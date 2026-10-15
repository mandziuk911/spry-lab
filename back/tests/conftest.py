import json
import os
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, Mock

import jwt
import pytest
from alembic import command
from alembic.config import Config
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

# Explicit offline configuration before importing the application, never a bypass.
os.environ["COGNITO_ISSUER"] = "https://cognito-idp.eu-north-1.amazonaws.com/eu-north-1_TestPool"
os.environ["COGNITO_CLIENT_ID"] = "testclient123"

from app import auth  # noqa: E402
from app.db import DB_CONNECT_ARGS, get_db  # noqa: E402
from app.main import app  # noqa: E402

BACK = Path(__file__).resolve().parents[1]


def migration_config(connection) -> Config:
    config = Config(str(BACK / "alembic.ini"))
    config.set_main_option("script_location", str(BACK / "alembic"))
    config.attributes["connection"] = connection
    return config


@pytest.fixture(scope="session")
def signing_keys():
    return {kid: rsa.generate_private_key(public_exponent=65537, key_size=2048) for kid in ("first", "next")}


@pytest.fixture
def token_factory(signing_keys):
    def create(*, kid="first", claims=None, remove=(), headers=None, key=None, algorithm="RS256"):
        payload = {
            "iss": os.environ["COGNITO_ISSUER"],
            "client_id": os.environ["COGNITO_CLIENT_ID"],
            "token_use": "access",
            "exp": int(time.time()) + 3600,
            "sub": "test-user",
            **(claims or {}),
        }
        for field in remove:
            payload.pop(field, None)
        return jwt.encode(
            payload, key or signing_keys[kid], algorithm=algorithm, headers={"kid": kid, **(headers or {})}
        )

    return create


@pytest.fixture(autouse=True)
def offline_jwks(monkeypatch, signing_keys):
    def document(kids=("first",)):
        keys = []
        for kid in kids:
            raw = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_keys[kid].public_key()))
            keys.append({**raw, "kid": kid, "alg": "RS256", "use": "sig"})
        return {"keys": keys}

    fetch = Mock(return_value=document())
    fetch.document = document
    monkeypatch.setattr(auth, "cache", auth.JWKSCache(os.environ["COGNITO_ISSUER"]))
    monkeypatch.setattr(auth, "fetch_jwks", fetch)
    return fetch


@pytest.fixture
def fake_db() -> MagicMock:
    return MagicMock(spec=Session)


@pytest.fixture
def client(fake_db, token_factory) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        with TestClient(app, headers={"Authorization": "Bearer " + token_factory()}) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def isolated_db() -> Iterator[Engine]:
    """Dedicated PostgreSQL test database only; additionally isolate each schema."""
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to dedicated spry_test PostgreSQL for integration tests")
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        pytest.fail("TEST_DATABASE_URL integration tests require PostgreSQL, not SQLite")
    if url.database != "spry_test":
        pytest.fail("Tests require dedicated database spry_test; application databases are forbidden")
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    schema = f"spry_test_{uuid.uuid4().hex}"
    admin = create_engine(url, connect_args=DB_CONNECT_ARGS)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    args = {**DB_CONNECT_ARGS, "options": DB_CONNECT_ARGS["options"] + f" -c search_path={schema}"}
    engine = create_engine(url, connect_args=args, pool_pre_ping=True, pool_timeout=3)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def postgres_client(isolated_db, token_factory) -> Iterator[TestClient]:
    with isolated_db.connect() as conn:
        command.upgrade(migration_config(conn), "head")
    factory = sessionmaker(bind=isolated_db, autoflush=False, expire_on_commit=False)

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app, headers={"Authorization": "Bearer " + token_factory()}) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
