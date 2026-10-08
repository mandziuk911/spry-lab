"""Fail-closed Cognito access-token verification; no application user/ownership state."""

import json
import re
import time
from http.client import HTTPException as HTTPTransportError
from threading import Lock
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, build_opener

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

CACHE_SECONDS = 300
REFRESH_SECONDS = 30
HTTP_TIMEOUT = 3
FETCH_SECONDS = 8
MAX_JWKS_BYTES = 65536
MAX_KEYS = 16
MAX_TOKEN_BYTES = 16384


class AuthUnavailable(Exception):
    """Trusted verification infrastructure unavailable (never log token details)."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AuthUnavailable


def fetch_jwks(url: str) -> dict:
    # Neither redirects nor token jku/x5u fields can change the trusted endpoint.
    deadline = time.monotonic() + FETCH_SECONDS
    try:
        with build_opener(NoRedirect()).open(url, timeout=HTTP_TIMEOUT) as response:
            body = bytearray()
            while True:
                if time.monotonic() >= deadline:
                    raise AuthUnavailable
                chunk = response.read1(min(8192, MAX_JWKS_BYTES + 1 - len(body)))
                body.extend(chunk)
                if len(body) > MAX_JWKS_BYTES:
                    raise AuthUnavailable
                if not chunk:
                    break
            return json.loads(body)
    except (URLError, OSError, ValueError, HTTPTransportError) as exc:
        raise AuthUnavailable from exc


class JWKSCache:
    """One bounded cache per process; serialized refresh and global bad-kid cooldown.

    Expired keys never authorize requests. Failed refreshes are negatively cached
    for 30 seconds; an unknown kid during that outage also fails closed with 503.
    Known, unexpired keys remain usable during a rotation-fetch outage.
    """

    def __init__(self, issuer: str):
        self.url = issuer + "/.well-known/jwks.json"
        self.keys: dict[str, jwt.PyJWK] = {}
        self.expires_at = 0.0
        self.refresh_after = 0.0
        self.failed = False
        self.lock = Lock()

    def key(self, kid: str) -> jwt.PyJWK:
        with self.lock:
            now = time.monotonic()
            if now < self.expires_at and kid in self.keys:
                return self.keys[kid]
            if now >= self.refresh_after:
                self.refresh_after = now + REFRESH_SECONDS
                try:
                    document = fetch_jwks(self.url)
                    raw_keys = document["keys"]
                    if not isinstance(raw_keys, list) or not 1 <= len(raw_keys) <= MAX_KEYS:
                        raise ValueError("Invalid key set")
                    keys = {}
                    for raw in raw_keys:
                        if raw.get("kty") != "RSA" or raw.get("alg") != "RS256":
                            continue
                        if raw.get("use", "sig") != "sig":
                            continue
                        key_id = raw.get("kid")
                        if not isinstance(key_id, str) or not 1 <= len(key_id) <= 256 or key_id in keys:
                            raise ValueError("Invalid key ID")
                        keys[key_id] = jwt.PyJWK.from_dict(raw, algorithm="RS256")
                    if not keys:
                        raise ValueError("No signing keys")
                    self.keys = keys
                    self.expires_at = time.monotonic() + CACHE_SECONDS
                    self.failed = False
                except (AuthUnavailable, ValueError, KeyError, TypeError, AttributeError, jwt.PyJWTError):
                    self.failed = True
                    raise AuthUnavailable from None
            if self.failed or time.monotonic() >= self.expires_at:
                raise AuthUnavailable
            if kid not in self.keys:
                raise jwt.InvalidTokenError("Unknown signing key")
            return self.keys[kid]


cache = JWKSCache(settings.cognito_issuer)
bearer = HTTPBearer(auto_error=False)


def unauthorized() -> HTTPException:
    return HTTPException(401, "Unauthorized", headers={"WWW-Authenticate": "Bearer"})


def require_access_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized()
    token = credentials.credentials
    if len(token) > MAX_TOKEN_BYTES or not re.fullmatch(
        r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", token
    ):
        raise unauthorized()
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if header.get("alg") != "RS256" or not isinstance(kid, str) or not 1 <= len(kid) <= 256:
            raise jwt.InvalidTokenError
        claims = jwt.decode(
            token,
            cache.key(kid).key,
            algorithms=["RS256"],
            issuer=settings.cognito_issuer,
            options={"require": ["exp", "iss", "token_use", "client_id"], "verify_aud": False},
        )
        if claims["token_use"] != "access" or claims["client_id"] != settings.cognito_client_id:
            raise jwt.InvalidTokenError
        # NumericDate must be a finite JSON number, not bool or a coercible string.
        if type(claims["exp"]) not in (int, float) or not 0 < claims["exp"] < float("inf"):
            raise jwt.InvalidTokenError
        return claims
    except AuthUnavailable:
        raise HTTPException(503, "Authentication service unavailable") from None
    except (jwt.PyJWTError, ValueError, TypeError, OverflowError):
        raise unauthorized() from None
