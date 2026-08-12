"""In-place schema upgrades.

Every other fixture in the suite builds a brand-new database, so migrations were only ever exercised
in their fresh-install form — while production upgrades an existing file with real rows in it. These
tests open a database at an older user_version and assert the upgrade lands.
"""

from __future__ import annotations

import sqlite3

import pytest

import app.db as db


@pytest.fixture
def at_v27(monkeypatch, tmp_path):
    """A database that looks like one created before the org_members.removed_at column existed."""
    path = tmp_path / "old.db"
    monkeypatch.setattr(db, "DB_PATH", path)
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()                                   # build the current schema...
    db.create_session("an existing chat", owner_id="someone")   # ...with real rows in it
    db.get_conn().close()
    db._conn = None

    raw = sqlite3.connect(path)
    raw.execute("ALTER TABLE org_members DROP COLUMN removed_at")
    raw.execute("PRAGMA user_version = 27")
    raw.commit()
    raw.close()
    monkeypatch.setattr(db, "_conn", None)
    return path


def _columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def test_upgrading_adds_removed_at_without_losing_data(at_v27):
    conn = db.get_conn()
    assert "removed_at" in _columns(conn, "org_members")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    assert db.list_sessions("someone"), "the upgrade must not lose existing rows"


def test_upgrading_is_idempotent(at_v27):
    db.get_conn().close()
    db._conn = None
    conn = db.get_conn()          # second open, already at the current version
    assert "removed_at" in _columns(conn, "org_members")


def test_one_accepted_membership_is_enforced_by_the_index_not_just_the_code(at_v27):
    """accept_invite checks this in Python, so dropping the partial unique index would change
    nothing in the suite — and 'which pool does this turn charge' would stop having an answer."""
    conn = db.get_conn()
    now = db._now()
    conn.execute("INSERT INTO orgs (id, name, owner_id, plan, created_at, is_demo) "
                 "VALUES ('o1','A','boss','institution',?,0)", (now,))
    conn.execute("INSERT INTO orgs (id, name, owner_id, plan, created_at, is_demo) "
                 "VALUES ('o2','B','boss2','institution',?,0)", (now,))
    conn.execute("INSERT INTO org_members (org_id, owner_id, role, invited_at, accepted_at) "
                 "VALUES ('o1','pupil','student',?,?)", (now, now))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO org_members (org_id, owner_id, role, invited_at, accepted_at) "
                     "VALUES ('o2','pupil','student',?,?)", (now, now))
