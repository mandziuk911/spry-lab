"""Reuse the main API's fail-closed RS256/Cognito/JWKS verifier, without a DB."""

from app.auth import unauthorized, verify_access_token


def verify_cognito_token(authorization: str) -> dict:
    if not isinstance(authorization, str):
        raise unauthorized()
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise unauthorized()
    claims = verify_access_token(parts[1])
    if not isinstance(claims.get("sub"), str) or not 1 <= len(claims["sub"]) <= 128:
        raise unauthorized()
    return claims
