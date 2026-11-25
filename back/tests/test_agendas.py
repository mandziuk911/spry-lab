import uuid

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from tests.conftest import migration_config
from tests.test_api import meeting_payload


def agenda_payload(**overrides):
    return {
        "title": "Planning",
        "starts_at": "2026-09-28T10:00:00+03:00",
        "duration_minutes": 60,
        "items": [{"topic": "Roadmap", "owner": "Alex", "minutes": 30}],
        "action_items": [{"task": "Send notes", "owner": None, "due": "2026-09-29"}],
        "language": "en",
        **overrides,
    }


def path(meeting_id=None):
    return f"/api/meetings/{meeting_id or uuid.uuid4()}/agenda"


@pytest.mark.parametrize("method", ["get", "post"])
def test_auth_required_before_storage(client, fake_db, method):
    client.headers.pop("Authorization")
    response = getattr(client, method)(path(), **({"json": agenda_payload()} if method == "post" else {}))
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    fake_db.get.assert_not_called()
    fake_db.scalar.assert_not_called()
    fake_db.execute.assert_not_called()


@pytest.mark.parametrize(
    "override",
    [
        {"title": "x" * 201},
        {"title": 42},
        {"starts_at": "2026-09-28T10:00:00"},
        {"starts_at": 1790582400},
        {"duration_minutes": True},
        {"duration_minutes": "60"},
        {"duration_minutes": 1.5},
        {"duration_minutes": 0},
        {"duration_minutes": 601},
        {"items": [{"topic": "   "}]},
        {"items": [{"topic": "x" * 1001}]},
        {"items": [{"topic": "Roadmap", "owner": "x" * 201}]},
        {"items": [{"topic": "Roadmap", "minutes": False}]},
        {"items": [{"topic": "Roadmap", "minutes": "2"}]},
        {"items": [{"topic": "Roadmap", "minutes": 481}]},
        {"items": [{"topic": "Roadmap", "minutes": 0}]},
        {"items": [{"topic": "Roadmap", "unknown": 1}]},
        {"items": [{"topic": "Roadmap"}] * 101},
        {"action_items": [{"task": ""}]},
        {"action_items": [{"task": "x" * 1001}]},
        {"action_items": [{"task": "Send notes", "owner": "x" * 201}]},
        {"action_items": [{"task": "Send notes", "due": "2026-02-30"}]},
        {"action_items": [{"task": "Send notes", "due": 1790582400}]},
        {"action_items": [{"task": "Send notes", "unknown": 1}]},
        {"action_items": [{"task": "Send notes"}] * 101},
        {"language": "  "},
        {"language": "x" * 1001},
        {"unknown": 1},
        {"ai_model": "model"},
        {"ai_suggestion": agenda_payload()},
        {"ai_suggestion": agenda_payload(), "ai_model": "model"},
        {"ai_suggestion": agenda_payload(), "ai_model": "", "ai_prompt_version": "v1"},
        {"ai_suggestion": agenda_payload(), "ai_model": "x" * 201, "ai_prompt_version": "v1"},
        {"ai_suggestion": agenda_payload(), "ai_model": "model", "ai_prompt_version": "x" * 201},
        {"ai_suggestion": agenda_payload(unknown=True), "ai_model": "model", "ai_prompt_version": "v1"},
    ],
)
def test_validation_before_storage(client, fake_db, override):
    response = client.post(path(), json=agenda_payload(**override))
    assert response.status_code == 422, response.text
    fake_db.scalar.assert_not_called()
    fake_db.execute.assert_not_called()
    fake_db.commit.assert_not_called()


@pytest.mark.parametrize("method, failure", [("get", "get"), ("post", "scalar"), ("post", "commit")])
def test_storage_failure_rolls_back(client, fake_db, method, failure):
    getattr(fake_db, failure).side_effect = OperationalError("secret SQL", {}, Exception("credentials"))
    response = getattr(client, method)(path(), **({"json": agenda_payload()} if method == "post" else {}))
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
    fake_db.rollback.assert_called_once()
    if failure == "commit":
        fake_db.commit.assert_called_once()


def test_unknown_and_missing_agenda(postgres_client):
    for method in ("get", "post"):
        response = getattr(postgres_client, method)(
            path(), **({"json": agenda_payload()} if method == "post" else {})
        )
        assert response.status_code == 404
        assert response.json() == {"detail": "Meeting not found"}
    meeting = postgres_client.post("/api/meetings", json=meeting_payload()).json()
    response = postgres_client.get(path(meeting["id"]))
    assert response.status_code == 404
    assert response.json() == {"detail": "Agenda not found"}


def test_roundtrip_update_and_cascade(postgres_client, isolated_db):
    meeting = postgres_client.post("/api/meetings", json=meeting_payload()).json()
    assert set(meeting) == {"id", "title", "starts_at", "ends_at", "attendee_count"}
    endpoint = path(meeting["id"])
    payload = agenda_payload(
        ai_suggestion=agenda_payload(title="Suggested title"), ai_model="test-model", ai_prompt_version="v1"
    )
    saved = postgres_client.post(endpoint, json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json() == payload
    assert postgres_client.get(endpoint).json() == payload

    manual = agenda_payload(title=None, starts_at=None, duration_minutes=None, items=[], action_items=[])
    expected = {**manual, "ai_suggestion": None, "ai_model": None, "ai_prompt_version": None}
    response = postgres_client.post(endpoint, json=manual)
    assert response.status_code == 200, response.text
    assert response.json() == expected
    assert postgres_client.get(endpoint).json() == expected
    with isolated_db.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM meeting_agendas")) == 1
        assert conn.scalar(text("SELECT ai_suggestion IS NULL FROM meeting_agendas")) is True
    assert postgres_client.delete(f"/api/meetings/{meeting['id']}").status_code == 204
    with isolated_db.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM meeting_agendas")) == 0


def test_forward_migration_and_scoped_downgrade(isolated_db):
    with isolated_db.connect() as conn:
        config = migration_config(conn)
        command.upgrade(config, "0004")
        meeting_id = conn.scalar(
            text(
                "INSERT INTO meetings (title, starts_at, ends_at, attendee_count) "
                "VALUES ('Keep me', '2026-09-28T07:00:00Z', '2026-09-28T08:00:00Z', 2) RETURNING id"
            )
        )
        conn.commit()
        command.upgrade(config, "0005")
        conn.execute(
            text("INSERT INTO meeting_agendas (meeting_id, agenda) VALUES (:id, '{}')"), {"id": meeting_id}
        )
        conn.commit()
        command.downgrade(config, "0004")
        assert "meeting_agendas" not in inspect(conn).get_table_names()
        assert conn.scalar(text("SELECT id FROM meetings")) == meeting_id
        conn.commit()
        command.upgrade(config, "0005")
        assert conn.scalar(text("SELECT count(*) FROM meeting_agendas")) == 0
