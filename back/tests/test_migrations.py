import uuid

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from tests.conftest import migration_config


def legacy_rows(conn, invalid_duration=False):
    ids = [uuid.uuid4(), uuid.uuid4()]
    owner = conn.scalar(
        text("INSERT INTO users (cognito_sub, email) VALUES ('legacy', 'legacy@example.com') RETURNING id")
    )
    for index, meeting_id in enumerate(ids):
        conn.execute(
            text(
                "INSERT INTO meetings (id, title, starts_at, ends_at, owner_id, description, place) "
                "VALUES (:id, :title, '2026-09-28T07:00:00Z', :end, :owner, 'legacy text', 'Room')"
            ),
            {
                "id": meeting_id,
                "title": f"Legacy {index}",
                "owner": owner,
                "end": "2026-09-28T06:00:00Z" if invalid_duration else "2026-09-28T08:00:00Z",
            },
        )
    for index in range(2):
        participant = conn.scalar(
            text("INSERT INTO participants (name, email) VALUES ('Guest', :email) RETURNING id"),
            {"email": f"guest{index}@example.com"},
        )
        conn.execute(
            text("INSERT INTO meeting_participants (meeting_id, participant_id) VALUES (:m, :p)"),
            {"m": ids[0], "p": participant},
        )
    conn.commit()
    return ids


def test_forward_migration_preserves_meetings_and_backfills(isolated_db):
    with isolated_db.connect() as conn:
        config = migration_config(conn)
        command.upgrade(config, "0003")
        ids = legacy_rows(conn)
        command.upgrade(config, "head")
        rows = conn.execute(text("SELECT id, title, attendee_count FROM meetings ORDER BY title")).all()
        assert [row.id for row in rows] == ids
        assert [row.title for row in rows] == ["Legacy 0", "Legacy 1"]
        assert [row.attendee_count for row in rows] == [2, 0]
        inspector = inspect(conn)
        assert set(inspector.get_table_names()) == {"alembic_version", "meetings"}
        assert {col["name"] for col in inspector.get_columns("meetings")} == {
            "id",
            "title",
            "starts_at",
            "ends_at",
            "attendee_count",
        }
        assert all(not col["nullable"] for col in inspector.get_columns("meetings"))
        conn.commit()
        with pytest.raises(RuntimeError, match="irreversible"):
            command.downgrade(config, "0003")
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "0004"
        after = conn.execute(text("SELECT id, title, attendee_count FROM meetings ORDER BY title")).all()
        assert after == rows
        assert set(inspect(conn).get_table_names()) == {"alembic_version", "meetings"}


@pytest.mark.parametrize(
    "count,end",
    [(-1, "2026-09-28T08:00:00Z"), (0, "2026-09-28T07:00:00Z"), (0, "2026-09-28T06:00:00Z")],
)
def test_database_constraints(isolated_db, count, end):
    with isolated_db.connect() as conn:
        command.upgrade(migration_config(conn), "head")
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO meetings (title, starts_at, ends_at, attendee_count) "
                    "VALUES ('Invalid', '2026-09-28T07:00:00Z', :end, :count)"
                ),
                {"end": end, "count": count},
            )
        conn.rollback()
        assert conn.scalar(text("SELECT count(*) FROM meetings")) == 0


def test_invalid_legacy_duration_aborts_without_data_loss(isolated_db):
    with isolated_db.connect() as conn:
        config = migration_config(conn)
        command.upgrade(config, "0003")
        ids = legacy_rows(conn, invalid_duration=True)
        with pytest.raises(IntegrityError):
            command.upgrade(config, "head")
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "0003"
        assert set(conn.scalars(text("SELECT id FROM meetings"))) == set(ids)
        assert conn.scalar(text("SELECT count(*) FROM meeting_participants")) == 2
        assert "attendee_count" not in {col["name"] for col in inspect(conn).get_columns("meetings")}
