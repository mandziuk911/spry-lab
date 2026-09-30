import uuid
from time import monotonic

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db import DB_CONNECT_ARGS, get_db
from app.main import app
from app.services.errors import DatabaseUnavailable, storage_operation
from tests.test_api import meeting_payload


def test_connection_refused_returns_bounded_503(client):
    unreachable = create_engine(
        "postgresql+psycopg://unused:unused@127.0.0.1:1/unused",
        connect_args=DB_CONNECT_ARGS,
        pool_pre_ping=True,
        pool_timeout=3,
    )

    def unavailable_db():
        with Session(unreachable) as session:
            yield session

    app.dependency_overrides[get_db] = unavailable_db
    try:
        started = monotonic()
        responses = [
            client.get("/api/meetings"),
            client.post("/api/meetings", json=meeting_payload()),
            client.delete(f"/api/meetings/{uuid.uuid4()}"),
            client.get("/api/health"),
        ]
        assert monotonic() - started < 16
        assert [r.status_code for r in responses] == [503, 503, 503, 503]
        assert all(response.json() == {"detail": "Database unavailable"} for response in responses[:3])
        assert responses[3].json() == {"status": "unavailable"}
    finally:
        unreachable.dispose()


def test_postgres_statement_timeout_rolls_back_and_recovers(isolated_db):
    with Session(isolated_db) as session:
        started = monotonic()
        with pytest.raises(DatabaseUnavailable), storage_operation(session):
            session.execute(text("SELECT pg_sleep(10)"))
        assert monotonic() - started < 8
        assert session.scalar(text("SELECT 1")) == 1
