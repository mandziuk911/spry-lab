import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db import DB_CONNECT_ARGS, engine
from app.main import app


def meeting_payload(**overrides):
    return {
        "title": "  Sprint planning  ",
        "starts_at": "2026-09-28T10:00:00+03:00",
        "ends_at": "2026-09-28T11:00:00+03:00",
        "attendee_count": 2,
        **overrides,
    }


@pytest.mark.parametrize(
    "override",
    [
        {"title": "   "},
        {"title": "x" * 201},
        {"title": 123},
        {"title": None},
        {"starts_at": "2026-09-28T10:00:00"},
        {"ends_at": "2026-09-28T11:00:00"},
        {"starts_at": "not-a-date"},
        {"starts_at": 1790582400},
        {"ends_at": "2026-09-28T07:00:00Z"},
        {"ends_at": "2026-09-28T06:00:00Z"},
        {"attendee_count": -1},
        {"attendee_count": True},
        {"attendee_count": False},
        {"attendee_count": "2"},
        {"attendee_count": 2.0},
        {"attendee_count": None},
        {"id": str(uuid.uuid4())},
        {"owner_id": str(uuid.uuid4())},
        {"participant_ids": []},
        {"place": "Room"},
        {"unexpected": 1},
    ],
)
def test_validation_before_write(client, fake_db, override):
    response = client.post("/api/meetings", json=meeting_payload(**override))
    assert response.status_code == 422, response.text
    assert isinstance(response.json()["detail"], list)
    fake_db.add.assert_not_called()
    fake_db.commit.assert_not_called()


@pytest.mark.parametrize("field", ["title", "starts_at", "ends_at", "attendee_count"])
def test_all_fields_required(client, fake_db, field):
    payload = meeting_payload()
    del payload[field]
    assert client.post("/api/meetings", json=payload).status_code == 422
    fake_db.commit.assert_not_called()


def test_active_routes_only():
    paths = app.openapi()["paths"]
    assert set(paths) == {"/api/meetings", "/api/health"}
    assert set(paths["/api/meetings"]) == {"get", "post"}


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("operation", ["list", "create", "health"])
def test_database_failure_is_generic_and_rolls_back(client, fake_db, operation, caplog):
    error = OperationalError("secret SQL", {"password": "secret"}, Exception("credentials"))
    if operation == "list":
        fake_db.scalars.side_effect = error
        response = client.get("/api/meetings")
    elif operation == "create":
        fake_db.commit.side_effect = error
        response = client.post("/api/meetings", json=meeting_payload())
        fake_db.commit.assert_called_once()  # An uncertain commit must not be retried.
    else:
        fake_db.execute.side_effect = error
        response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == (
        {"status": "unavailable"} if operation == "health" else {"detail": "Database unavailable"}
    )
    fake_db.rollback.assert_called_once()
    assert "secret" not in caplog.text
    assert "credentials" not in caplog.text


def test_rollback_failure_keeps_503(client, fake_db):
    error = OperationalError("secret", {}, Exception("secret"))
    fake_db.scalars.side_effect = error
    fake_db.rollback.side_effect = error
    assert client.get("/api/meetings").status_code == 503


def test_connection_and_query_timeouts_are_bounded():
    assert engine.pool._pre_ping
    assert engine.pool.timeout() == 3
    assert DB_CONNECT_ARGS["connect_timeout"] == 3
    assert "statement_timeout=3000" in DB_CONNECT_ARGS["options"]
    assert "lock_timeout=2000" in DB_CONNECT_ARGS["options"]
    assert DB_CONNECT_ARGS["tcp_user_timeout"] == 5000


def test_postgres_create_list_persistence_order(postgres_client, isolated_db):
    client = postgres_client
    assert client.get("/api/meetings").json() == []
    assert client.get("/api/health").json() == {"status": "ok"}
    created = []
    for count in (0, 5):
        response = client.post("/api/meetings", json=meeting_payload(attendee_count=count))
        assert response.status_code == 201, response.text
        meeting = response.json()
        assert set(meeting) == {"id", "title", "starts_at", "ends_at", "attendee_count"}
        assert str(uuid.UUID(meeting["id"])) == meeting["id"]
        assert meeting["title"] == "Sprint planning"
        assert meeting["starts_at"] == "2026-09-28T07:00:00Z"
        assert meeting["ends_at"] == "2026-09-28T08:00:00Z"
        assert meeting["attendee_count"] == count
        created.append(meeting)
    later = client.post(
        "/api/meetings",
        json=meeting_payload(starts_at="2026-10-01T10:00:00Z", ends_at="2026-10-01T11:00:00Z"),
    ).json()
    expected = sorted(created, key=lambda m: m["id"]) + [later]
    assert client.get("/api/meetings").json() == expected
    # An independent connection proves committed persistence, not a request-local fake.
    with isolated_db.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM meetings")) == 3
    isolated_db.dispose()  # Simulate loss of the old connection pool / new requests.
    assert client.get("/api/meetings").json() == expected
    assert client.post("/api/meetings", json=meeting_payload(attendee_count="1")).status_code == 422
    assert len(client.get("/api/meetings").json()) == 3


def test_postgres_unavailable_then_recovers(client, fake_db, isolated_db):
    # Missing table is a real PostgreSQL storage failure; rollback permits a new request.
    from sqlalchemy.orm import Session

    from app.db import get_db

    with Session(isolated_db) as session:
        app.dependency_overrides[get_db] = lambda: session
        response = client.get("/api/meetings")
        assert response.status_code == 503
        assert response.json() == {"detail": "Database unavailable"}
        assert client.get("/api/health").json() == {"status": "ok"}
