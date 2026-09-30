import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import settings
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
    assert set(paths) == {"/api/meetings", "/api/meetings/{meeting_id}", "/api/health"}
    assert set(paths["/api/meetings"]) == {"get", "post"}
    assert set(paths["/api/meetings/{meeting_id}"]) == {"delete"}


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("operation", ["list", "create", "delete", "delete_commit", "health"])
def test_database_failure_is_generic_and_rolls_back(client, fake_db, operation, caplog):
    error = OperationalError("secret SQL", {"password": "secret"}, Exception("credentials"))
    if operation == "list":
        fake_db.scalars.side_effect = error
        response = client.get("/api/meetings")
    elif operation == "create":
        fake_db.commit.side_effect = error
        response = client.post("/api/meetings", json=meeting_payload())
        fake_db.commit.assert_called_once()  # An uncertain commit must not be retried.
    elif operation in {"delete", "delete_commit"}:
        if operation == "delete":
            fake_db.scalar.side_effect = error
        else:
            fake_db.commit.side_effect = error
        response = client.delete(f"/api/meetings/{uuid.uuid4()}")
        fake_db.scalar.assert_called_once()
        if operation == "delete_commit":
            fake_db.commit.assert_called_once()  # No retry of an uncertain deletion.
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


@pytest.mark.parametrize("operation", ["list", "delete"])
def test_rollback_failure_keeps_503(client, fake_db, operation):
    error = OperationalError("secret", {}, Exception("secret"))
    fake_db.rollback.side_effect = error
    if operation == "list":
        fake_db.scalars.side_effect = error
        response = client.get("/api/meetings")
    else:
        fake_db.scalar.side_effect = error
        response = client.delete(f"/api/meetings/{uuid.uuid4()}")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
    fake_db.rollback.assert_called_once()


def test_delete_cors_preflight_allows_only_configured_origin(client, fake_db):
    origin = settings.cors_origin_list[0]
    headers = {"Origin": origin, "Access-Control-Request-Method": "DELETE"}
    response = client.options(f"/api/meetings/{uuid.uuid4()}", headers=headers)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "DELETE" in response.headers["access-control-allow-methods"]
    denied = client.options(
        f"/api/meetings/{uuid.uuid4()}",
        headers={**headers, "Origin": "https://untrusted.example"},
    )
    assert denied.status_code == 400
    assert "access-control-allow-origin" not in denied.headers
    fake_db.scalar.assert_not_called()


def test_delete_malformed_uuid_before_write(client, fake_db):
    response = client.delete("/api/meetings/not-a-uuid")
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    fake_db.scalar.assert_not_called()
    fake_db.commit.assert_not_called()


def test_postgres_delete_persists_and_retains_other_meeting(postgres_client, isolated_db):
    deleted = postgres_client.post("/api/meetings", json=meeting_payload()).json()
    retained = postgres_client.post("/api/meetings", json=meeting_payload(title="Keep me")).json()
    response = postgres_client.delete(f"/api/meetings/{deleted['id']}")
    assert response.status_code == 204
    assert response.content == b""
    assert postgres_client.get("/api/meetings").json() == [retained]
    with Session(isolated_db) as session:
        assert list(session.scalars(text("SELECT id FROM meetings"))) == [uuid.UUID(retained["id"])]
    isolated_db.dispose()
    assert postgres_client.get("/api/meetings").json() == [retained]
    for meeting_id in (deleted["id"], str(uuid.uuid4())):
        response = postgres_client.delete(f"/api/meetings/{meeting_id}")
        assert response.status_code == 404
        assert response.json() == {"detail": "Meeting not found"}
    assert postgres_client.get("/api/meetings").json() == [retained]


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


@pytest.mark.parametrize("operation", ["list", "delete"])
def test_postgres_unavailable_then_recovers(client, fake_db, isolated_db, operation):
    # Missing table is a real PostgreSQL storage failure; rollback permits a new request.

    from app.db import get_db

    with Session(isolated_db) as session:
        app.dependency_overrides[get_db] = lambda: session
        response = (
            client.get("/api/meetings")
            if operation == "list"
            else client.delete(f"/api/meetings/{uuid.uuid4()}")
        )
        assert response.status_code == 503
        assert response.json() == {"detail": "Database unavailable"}
        assert client.get("/api/health").json() == {"status": "ok"}
