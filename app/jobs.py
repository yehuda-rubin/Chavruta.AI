"""In-process async job registry for long-running generation.

Why this exists: a full lesson can take minutes on the LLM — longer than the 504 window of any proxy
in front of the API (nginx, a cloud load balancer, Cloudflare). Holding the HTTP request open that
long means the gateway kills it and the user sees a 504 even though the answer was being written.

The fix is the standard pattern: the async endpoints SUBMIT the work here and return a job id
immediately (202); the client polls `GET /jobs/{id}` on a short interval until it flips to done/error.
No single request stays open long enough to trip a proxy timeout.

Single-instance, in-memory — deliberately, and for the same reason as the rate limiter in
`app.security`: this deployment is one FastAPI process. Jobs live in this process's memory; a restart
drops them (the client just re-submits). Behind multiple replicas you'd move this to a shared queue
(Redis + RQ/Celery) so any replica can serve the poll — noted, not built, because one instance
doesn't need it (Principle: no speculative infrastructure).
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

_log = logging.getLogger("chavruta.jobs")


@dataclass
class Job:
    """One unit of async work. `result` is whatever the submitted callable returned (already a
    JSON-serialisable dict in our use), `error` is a human-readable string on failure. `owner` scopes
    polling — a job is only visible to the identity that created it."""

    id: str
    owner: str
    status: str = "pending"      # pending | running | done | error
    result: Any = None
    error: str | None = None
    created_at: float = 0.0
    finished_at: float = 0.0


class JobRegistry:
    """Thread-safe submit/poll over a small thread pool.

    The pool is intentionally tiny: generation is the expensive resource (LLM tokens + the single
    embedder/Qdrant client), so running many lessons at once buys nothing and risks memory pressure —
    excess submissions queue and run as workers free up. A background reap on submit drops finished
    jobs past their TTL so the dict can't grow without bound.
    """

    def __init__(self, max_workers: int = 2, ttl_s: float = 3600.0):
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="job")
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_s

    def submit(self, owner: str, fn: Callable[[], Any]) -> str:
        """Register a job, hand `fn` to the pool, and return the job id at once. `fn` is called with
        no arguments and must return a JSON-serialisable value; any exception is captured onto the
        job as an error (never crashes the worker thread)."""
        now = time.time()
        self._reap(now)
        jid = uuid.uuid4().hex[:16]
        job = Job(id=jid, owner=owner, created_at=now)
        with self._lock:
            self._jobs[jid] = job

        def _run() -> None:
            with self._lock:
                job.status = "running"
            try:
                res = fn()
            except Exception as exc:            # noqa: BLE001 — a failed job must not kill the worker
                _log.exception("job %s FAILED", jid)
                with self._lock:
                    job.error = str(exc) or exc.__class__.__name__
                    job.status = "error"
                    job.finished_at = time.time()
                return
            with self._lock:
                job.result = res
                job.status = "done"
                job.finished_at = time.time()

        self._pool.submit(_run)
        return jid

    def get(self, jid: str, owner: str) -> Job | None:
        """Return the job iff it exists AND belongs to `owner` — otherwise None, so a caller can never
        poll (or read the result of) another identity's job. The route maps None to a 404."""
        with self._lock:
            job = self._jobs.get(jid)
            if job is None or job.owner != owner:
                return None
            return job

    def _reap(self, now: float) -> None:
        with self._lock:
            stale = [k for k, j in self._jobs.items()
                     if j.finished_at and now - j.finished_at > self._ttl]
            for k in stale:
                del self._jobs[k]


# Module-level singleton — the app shares one registry (like the rate-limiter windows). Small pool by
# design (see class docstring); TTL keeps finished jobs pollable for an hour after they complete.
registry = JobRegistry(max_workers=2, ttl_s=3600.0)
