"""Guard findings: the storage behind the admin panel's quality-control screen.

The three watching checks add nothing a user sees, so this table is the ONLY place their findings
survive. If it silently drops rows, the decision it exists to inform — "has this guard earned the
right to warn a user?" — gets made on an empty screen that looks like good news.
"""
from __future__ import annotations

import sqlite3

import pytest

import app.db as db
from chavruta.generation import guards


@pytest.fixture
def fresh_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "guards.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    yield db
    guards.set_sink(None)


def test_a_finding_round_trips_with_its_detail_parsed(fresh_db):
    fresh_db.record_guard_finding("misattribution", "qa",
                                  {"claimed": "rashi", "found_in": "tosafot", "quote": "ולעולם"})
    row = fresh_db.list_guard_findings()[0]
    assert row["kind"] == "misattribution" and row["intent"] == "qa"
    # Parsed, not a JSON string: a caller that has to decode every row will one day forget to and
    # render a blob at the operator.
    assert row["detail"]["claimed"] == "rashi"


def test_counts_are_per_kind(fresh_db):
    for kind in ("misattribution", "misattribution", "deontic"):
        fresh_db.record_guard_finding(kind, "qa", {"x": "1"})
    assert fresh_db.guard_finding_counts() == {"misattribution": 2, "deontic": 1}


def test_filtering_by_kind_and_window(fresh_db):
    fresh_db.record_guard_finding("deontic", "qa", {"x": "1"}, at="2026-01-01T00:00:00+00:00")
    fresh_db.record_guard_finding("calendar", "lesson", {"x": "2"}, at="2026-08-13T00:00:00+00:00")
    assert len(fresh_db.list_guard_findings(kind="calendar")) == 1
    assert len(fresh_db.list_guard_findings(since="2026-06-01T00:00:00+00:00")) == 1


def test_the_sink_is_what_connects_the_engine_to_storage(fresh_db):
    """Nothing under src/chavruta imports app.*, so the web layer registers a writer. Before it
    does, a report must be a silent no-op — the CLI and the tests have no database at all."""
    guards.report("deontic", "qa", {"authority": "rambam"})
    assert fresh_db.list_guard_findings() == []

    guards.set_sink(fresh_db.record_guard_finding)
    guards.report("deontic", "qa", {"authority": "rambam"})
    assert fresh_db.list_guard_findings()[0]["detail"]["authority"] == "rambam"


def test_an_unknown_kind_is_dropped_not_stored(fresh_db):
    """A typo would create a category the panel never renders — invisible, and indistinguishable
    from the guard never firing."""
    guards.set_sink(fresh_db.record_guard_finding)
    guards.report("misatribution", "qa", {"x": "1"})       # note the typo
    assert fresh_db.list_guard_findings() == []


def test_a_failing_sink_cannot_break_the_answer(fresh_db):
    """This runs on the generation path. A diagnostic that can raise into a user's answer is worse
    than a diagnostic nobody has."""
    def explode(kind, intent, detail):
        raise RuntimeError("storage is down")

    guards.set_sink(explode)
    guards.report("deontic", "qa", {"authority": "rambam"})   # must not raise


def test_a_failing_insert_logs_instead_of_raising(fresh_db, monkeypatch, caplog):
    """The except branch inside record_guard_finding used a logger this module has never had, so the
    one line meant to keep a diagnostic from breaking a request was itself a NameError. It never
    fired in a test because it only runs when the insert fails."""
    import logging

    def broken_tx(_conn):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(fresh_db, "_tx", broken_tx)
    with caplog.at_level(logging.ERROR, logger="chavruta.telemetry"):
        fresh_db.record_guard_finding("deontic", "qa", {"authority": "rambam"})   # must not raise
    assert any("guard finding" in r.getMessage() for r in caplog.records)
