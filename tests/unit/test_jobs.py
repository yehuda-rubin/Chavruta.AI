"""Async job registry (app/jobs.py): the queue that keeps long lessons from tripping a proxy 504.

The guarantees pinned here: a submitted job actually runs and captures its return value; a failing
job is recorded as an error instead of crashing the worker; polling is owner-scoped (one identity
can't read another's job or result); and finished jobs are reaped past their TTL so the registry
can't grow without bound.
"""
from __future__ import annotations

import time

import pytest
from app.jobs import Job, JobRegistry


def _await(reg: JobRegistry, jid: str, owner: str, *, timeout: float = 5.0) -> Job:
    """Block until the job leaves pending/running (or the timeout trips)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = reg.get(jid, owner)
        assert job is not None
        if job.status in ("done", "error"):
            return job
        time.sleep(0.01)
    raise AssertionError(f"job {jid} did not finish within {timeout}s")


def test_job_runs_and_returns_result():
    reg = JobRegistry(max_workers=2)
    jid = reg.submit("alice", lambda: {"answer": 42})
    job = _await(reg, jid, "alice")
    assert job.status == "done"
    assert job.result == {"answer": 42}
    assert job.error is None


def test_failing_job_captured_as_error():
    reg = JobRegistry(max_workers=2)

    def boom():
        raise ValueError("kaboom")

    jid = reg.submit("alice", boom)
    job = _await(reg, jid, "alice")
    assert job.status == "error"
    assert "kaboom" in job.error
    assert job.result is None


def test_poll_is_owner_scoped():
    reg = JobRegistry(max_workers=2)
    jid = reg.submit("alice", lambda: "secret lesson")
    _await(reg, jid, "alice")
    # Bob must not be able to see (or read the result of) Alice's job.
    assert reg.get(jid, "bob") is None
    assert reg.get(jid, "alice") is not None


def test_unknown_job_is_none():
    reg = JobRegistry()
    assert reg.get("does-not-exist", "alice") is None


def test_finished_jobs_reaped_past_ttl():
    reg = JobRegistry(max_workers=2, ttl_s=0.05)
    jid = reg.submit("alice", lambda: 1)
    _await(reg, jid, "alice")
    time.sleep(0.1)                      # let the job age past the TTL
    reg.submit("alice", lambda: 2)       # submit() reaps stale finished jobs first
    assert reg.get(jid, "alice") is None  # the old job is gone


def test_many_jobs_all_complete():
    """The pool is tiny (2 workers) but excess submissions must still all run to completion."""
    reg = JobRegistry(max_workers=2)
    ids = [reg.submit("alice", (lambda n=n: n * n)) for n in range(10)]
    results = {reg.get(jid, "alice").result if False else _await(reg, jid, "alice").result
               for jid in ids}
    assert results == {n * n for n in range(10)}


def test_job_cancellation_and_session_lookup():
    reg = JobRegistry(max_workers=2)
    ev = time.sleep

    # Submit a job attached to session_123
    jid = reg.submit("alice", lambda: ev(0.5) or {"status": "ok"}, session_id="session_123")
    active = reg.get_active_for_session("session_123", "alice")
    assert active is not None
    assert active.id == jid
    assert active.session_id == "session_123"

    # Cancel the job
    assert reg.cancel(jid, "alice") is True
    job = reg.get(jid, "alice")
    assert job.status == "cancelled"
    assert job.cancel_event.is_set()

    # Active session lookup now returns None
    assert reg.get_active_for_session("session_123", "alice") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

