import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import DB_CONNECT_ARGS, get_db
from app.main import app

BACK = Path(__file__).resolve().parents[1]


def migration_config(connection) -> Config:
    config = Config(str(BACK / "alembic.ini"))
    config.set_main_option("script_location", str(BACK / "alembic"))
    config.attributes["connection"] = connection
    return config


@pytest.fixture
def fake_db() -> MagicMock:
    return MagicMock(spec=Session)


@pytest.fixture
def client(fake_db) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def isolated_db() -> Iterator[Engine]:
    """Real PostgreSQL only. Never migrate/drop tables in an application's schema."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("Set DATABASE_URL to a dedicated PostgreSQL test database for integration tests")
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        pytest.fail("DATABASE_URL integration tests require PostgreSQL, not SQLite")
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
def postgres_client(isolated_db) -> Iterator[TestClient]:
    with isolated_db.connect() as conn:
        command.upgrade(migration_config(conn), "head")
    factory = sessionmaker(bind=isolated_db, autoflush=False, expire_on_commit=False)

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
