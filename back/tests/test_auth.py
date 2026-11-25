import io
import json
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import jwt
import pytest
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from app import auth
from app.config import Settings


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/meetings"),
        ("post", "/api/meetings"),
        ("delete", "/api/meetings/00000000-0000-0000-0000-000000000001"),
        ("delete", "/api/meetings/not-a-uuid"),
    ],
)
@pytest.mark.parametrize("credential", [None, "", "Basic abc", "Bearer", "Bearer bad", "Bearer a.b.c extra"])
def test_missing_malformed_credentials_before_storage(
    client,
    fake_db,
    offline_jwks,
    method,
    path,
    credential,
):
    client.headers.pop("Authorization")
    headers = {} if credential is None else {"Authorization": credential}
    response = getattr(client, method)(path, headers=headers)
    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}
    assert response.headers["www-authenticate"] == "Bearer"
    assert not fake_db.mock_calls
    offline_jwks.assert_not_called()


@pytest.mark.parametrize(
    "claims,remove",
    [
        ({"exp": int(time.time()) - 10}, ()),
        ({"exp": "9999999999"}, ()),
        ({"exp": True}, ()),
        ({"exp": None}, ()),
        ({"exp": float("inf")}, ()),
        ({"exp": float("nan")}, ()),
        ({"iss": "https://attacker.example/pool"}, ()),
        ({"client_id": "wrongclient"}, ()),
        ({"token_use": "id"}, ()),
        ({"token_use": None}, ()),
        ({"client_id": ["testclient123"]}, ()),
        ({"nbf": int(time.time()) + 3600}, ()),
        ({"iat": int(time.time()) + 3600}, ()),
        ({}, ("exp",)),
        ({}, ("iss",)),
        ({}, ("client_id",)),
        ({}, ("token_use",)),
    ],
)
def test_invalid_claims(client, fake_db, token_factory, claims, remove, caplog):
    token = token_factory(claims=claims, remove=remove)
    response = client.get("/api/meetings", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}
    assert response.headers["www-authenticate"] == "Bearer"
    assert not fake_db.mock_calls
    assert token not in caplog.text


def test_signature_algorithms_and_header(client, fake_db, token_factory, signing_keys, offline_jwks):
    original = token_factory()
    _, payload, signature = original.split(".")
    malformed_headers = []
    for header in ({"alg": "RS256"}, {"alg": "RS256", "kid": None}, {"alg": "RS256", "kid": 123}):
        encoded = jwt.utils.base64url_encode(json.dumps(header).encode()).decode()
        malformed_headers.append(f"{encoded}.{payload}.{signature}")
    tampered_payload = jwt.utils.base64url_encode(b'{"exp":9999999999,"token_use":"access"}').decode()
    tokens = [
        *malformed_headers,
        f"{original.split('.')[0]}.{tampered_payload}.{signature}",
        token_factory(key=signing_keys["next"]),
        token_factory(algorithm="HS256", key="sufficiently-long-hmac-secret-for-test"),
        token_factory(algorithm="RS512"),
        token_factory(headers={"kid": "x" * 257}),
        jwt.encode({"exp": int(time.time()) + 100}, "", algorithm="none"),
        "x" * (auth.MAX_TOKEN_BYTES + 1),
    ]
    for token in tokens:
        response = client.get("/api/meetings", headers={"Authorization": "Bearer " + token})
        assert response.status_code == 401
    assert not fake_db.mock_calls
    assert offline_jwks.call_count == 1


def test_shared_users_and_never_token_url(client, fake_db, token_factory, offline_jwks):
    fake_db.scalars.return_value.all.return_value = []
    for sub in ("password-user", "google-user"):
        token = token_factory(claims={"sub": sub}, headers={"jku": "https://attacker.example/keys"})
        assert client.get("/api/meetings", headers={"Authorization": "bEaReR " + token}).status_code == 200
    assert fake_db.scalars.call_count == 2
    offline_jwks.assert_called_once_with(auth.cache.url)
    assert auth.cache.url == auth.settings.cognito_issuer + "/.well-known/jwks.json"


def test_cache_expiry_rotation_and_unknown_kid(client, token_factory, offline_jwks, fake_db, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: clock[0])
    fake_db.scalars.return_value.all.return_value = []
    assert client.get("/api/meetings").status_code == 200
    next_headers = {"Authorization": "Bearer " + token_factory(kid="next")}
    for index in range(20):
        # Unique attacker-chosen kids cannot bypass the global refresh throttle.
        unknown = token_factory(headers={"kid": f"unknown-{index}"})
        assert client.get("/api/meetings", headers={"Authorization": "Bearer " + unknown}).status_code == 401
    assert client.get("/api/meetings", headers=next_headers).status_code == 401
    assert offline_jwks.call_count == 1
    clock[0] += auth.REFRESH_SECONDS
    offline_jwks.return_value = offline_jwks.document(("first", "next"))
    assert client.get("/api/meetings", headers=next_headers).status_code == 200
    assert offline_jwks.call_count == 2
    clock[0] += auth.CACHE_SECONDS
    offline_jwks.return_value = offline_jwks.document(("next",))
    assert client.get("/api/meetings", headers=next_headers).status_code == 200
    assert client.get("/api/meetings").status_code == 401  # Removed key no longer trusted.
    assert offline_jwks.call_count == 3


def test_refresh_serialized_across_concurrent_requests(offline_jwks):
    with ThreadPoolExecutor(max_workers=8) as pool:
        keys = list(pool.map(auth.cache.key, ["first"] * 24))
    assert len(keys) == 24
    offline_jwks.assert_called_once()


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"keys": []},
        {"keys": "bad"},
        {"keys": [{}] * 17},
        {"keys": [None]},
        {"keys": [{"kty": "RSA", "alg": "RS256", "kid": "bad"}]},
    ],
)
def test_bad_jwks_fail_closed(client, fake_db, offline_jwks, document):
    offline_jwks.return_value = document
    response = client.get("/api/meetings")
    assert response.status_code == 503
    assert response.json() == {"detail": "Authentication service unavailable"}
    assert not fake_db.mock_calls


def test_network_failure_cooldown_and_recovery(client, offline_jwks, fake_db, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: clock[0])
    offline_jwks.side_effect = auth.AuthUnavailable
    for _ in range(20):
        response = client.get("/api/meetings")
        assert response.status_code == 503
        assert response.json() == {"detail": "Authentication service unavailable"}
    assert not fake_db.mock_calls
    assert offline_jwks.call_count == 1
    clock[0] += auth.REFRESH_SECONDS
    offline_jwks.side_effect = None
    fake_db.scalars.return_value.all.return_value = []
    assert client.get("/api/meetings").status_code == 200
    assert offline_jwks.call_count == 2
    clock[0] += auth.CACHE_SECONDS
    offline_jwks.side_effect = auth.AuthUnavailable
    assert client.get("/api/meetings").status_code == 503  # No stale authorization.


def test_known_keys_usable_but_unknown_fail_closed_during_outage(
    client,
    offline_jwks,
    fake_db,
    monkeypatch,
    token_factory,
):
    clock = [1000.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: clock[0])
    fake_db.scalars.return_value.all.return_value = []
    assert client.get("/api/meetings").status_code == 200
    clock[0] += auth.REFRESH_SECONDS
    offline_jwks.side_effect = auth.AuthUnavailable
    headers = {"Authorization": "Bearer " + token_factory(kid="next")}
    assert client.get("/api/meetings", headers=headers).status_code == 503
    assert client.get("/api/meetings", headers=headers).status_code == 503
    assert client.get("/api/meetings").status_code == 200
    assert offline_jwks.call_count == 2


@pytest.mark.parametrize("path", ["/api/health", "/api/docs", "/api/openapi.json"])
def test_public_routes_without_credentials(client, offline_jwks, path):
    client.headers.pop("Authorization")
    offline_jwks.side_effect = auth.AuthUnavailable
    assert client.get(path).status_code == 200
    offline_jwks.assert_not_called()


def test_public_health_still_checks_db(client, fake_db, offline_jwks):
    client.headers.pop("Authorization")
    fake_db.execute.side_effect = OperationalError("private SQL", {}, Exception("private"))
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    fake_db.execute.assert_called_once()
    offline_jwks.assert_not_called()


def test_authorization_preflight_public(client, offline_jwks):
    client.headers.pop("Authorization")
    response = client.options(
        "/api/meetings",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )
    assert response.status_code == 200
    assert "authorization" in response.headers["access-control-allow-headers"].lower()
    offline_jwks.assert_not_called()


@pytest.mark.parametrize(
    "issuer",
    [
        "",
        "http://cognito-idp.eu-north-1.amazonaws.com/eu-north-1_Test",
        "https://attacker.example/eu-north-1_Test",
        "https://cognito-idp.eu-north-1.amazonaws.com/us-east-1_Test",
        "https://cognito-idp.eu-north-1.amazonaws.com/eu-north-1_Test?foo=1",
        "https://cognito-idp.eu-north-1.amazonaws.com/eu-north-1_Test/",
    ],
)
def test_untrusted_issuer_config_rejected(issuer):
    with pytest.raises(ValidationError, match="COGNITO_ISSUER"):
        Settings(cognito_issuer=issuer, cognito_client_id="testclient123", _env_file=None)


def test_missing_partial_config(monkeypatch):
    for field in ("COGNITO_ISSUER", "COGNITO_CLIENT_ID"):
        monkeypatch.delenv(field)
    with pytest.raises(ValidationError, match="cognito_issuer"):
        Settings(_env_file=None)
    monkeypatch.setenv("COGNITO_ISSUER", auth.settings.cognito_issuer)
    with pytest.raises(ValidationError, match="cognito_client_id"):
        Settings(_env_file=None)
    with pytest.raises(ValidationError, match="COGNITO_CLIENT_ID"):
        Settings(cognito_client_id="", _env_file=None)


def test_https_fetch_timeout_size_json_and_redirect(monkeypatch):
    # Exercise the real transport wrapper without internet or token material.
    from urllib.error import URLError

    opener = Mock()
    monkeypatch.setattr(auth, "build_opener", lambda handler: opener)
    # autouse mock replaced only here to exercise the real function via saved implementation.
    from http.client import IncompleteRead

    for error in (TimeoutError(), URLError("private error"), IncompleteRead(b"")):
        opener.open.side_effect = error
        with pytest.raises(auth.AuthUnavailable):
            REAL_FETCH(auth.cache.url)
    opener.open.side_effect = None
    for data in (b"not-json", b"x" * (auth.MAX_JWKS_BYTES + 1)):
        opener.open.return_value = io.BytesIO(data)
        with pytest.raises(auth.AuthUnavailable):
            REAL_FETCH(auth.cache.url)
    opener.open.return_value = io.BytesIO(b'{"keys": []}')
    assert REAL_FETCH(auth.cache.url) == {"keys": []}
    opener.open.assert_called_with(auth.cache.url, timeout=auth.HTTP_TIMEOUT)
    with pytest.raises(auth.AuthUnavailable):
        auth.NoRedirect().redirect_request(None, None, 302, "", {}, "https://attacker.example")


@pytest.mark.parametrize("url", ["postgresql+psycopg://spry:spry@db/spry", "sqlite:///spry_test"])
def test_integration_database_guard(monkeypatch, url):
    from tests.conftest import isolated_db

    monkeypatch.setenv("TEST_DATABASE_URL", url)
    with pytest.raises(pytest.fail.Exception):
        next(isolated_db.__wrapped__())


def test_fetch_total_deadline(monkeypatch):
    opener = Mock()
    opener.open.return_value = io.BytesIO(b'{"keys": []}')
    monkeypatch.setattr(auth, "build_opener", lambda handler: opener)
    clock = iter((1000.0, 1000.0 + auth.FETCH_SECONDS))
    monkeypatch.setattr(auth.time, "monotonic", lambda: next(clock))
    with pytest.raises(auth.AuthUnavailable):
        REAL_FETCH(auth.cache.url)


REAL_FETCH = auth.fetch_jwks
