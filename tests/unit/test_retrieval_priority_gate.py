"""_PriorityGate — the CPU-bound retrieval concurrency gate (2026-08-19).

Split out of app/api.py's one whole-request semaphore once real production data showed the CPU-
bound part of a request (embedding + Qdrant, 0.6-8.7s measured) is a small fraction of its total
wall time (median 30s, mean 45.8s) — the rest is waiting on the LLM API over the network, holding
no CPU. Gating the WHOLE request meant most of a "busy" system was actually idle CPU sitting behind
requests that were just waiting on Nebius.

The operator additionally asked that a request already mid-conversation — the model replied
===NEED_SOURCES=== and is waiting on a follow-up retrieval to CONTINUE work it already spent a
round and real tokens on — must not queue behind a brand-new question's first retrieval, which has
no sunk cost. Plain threading.Semaphore cannot express that (release order is unspecified), hence
this class.
"""
from __future__ import annotations

import threading
import time

from chavruta.retrieval.hybrid import _PriorityGate


def test_capacity_is_enforced_under_real_concurrent_load():
    """The actual property that matters: however many threads hammer the gate, at most `capacity`
    are ever inside it at once."""
    gate = _PriorityGate(capacity=3)
    in_use = 0
    peak = 0
    lock = threading.Lock()

    def worker():
        nonlocal in_use, peak
        with gate.acquire():
            with lock:
                in_use += 1
                peak = max(peak, in_use)
            time.sleep(0.02)
            with lock:
                in_use -= 1

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert peak <= 3, f"capacity=3 was violated: saw {peak} concurrent holders"
    assert in_use == 0, "a slot leaked — not every acquire was released"


def test_a_priority_waiter_is_served_before_an_earlier_normal_waiter():
    """The whole point. A normal request grabs every slot; a normal waiter and a priority waiter
    both then queue behind it (priority arriving second, i.e. objectively later) — the priority
    waiter must still be admitted first once a slot frees."""
    gate = _PriorityGate(capacity=1)
    order: list[str] = []
    order_lock = threading.Lock()
    holder_ready = threading.Event()
    release_holder = threading.Event()
    normal_queued = threading.Event()

    def holder():
        with gate.acquire():
            holder_ready.set()
            release_holder.wait(timeout=5)

    def normal_waiter():
        holder_ready.wait(timeout=5)
        with gate.acquire(priority=False):
            with order_lock:
                order.append("normal")

    def priority_waiter():
        holder_ready.wait(timeout=5)
        normal_queued.wait(timeout=5)   # guarantee normal queued FIRST, chronologically
        with gate.acquire(priority=True):
            with order_lock:
                order.append("priority")

    t_holder = threading.Thread(target=holder)
    t_holder.start()
    holder_ready.wait(timeout=5)

    t_normal = threading.Thread(target=normal_waiter)
    t_normal.start()
    time.sleep(0.05)                    # let the normal thread actually block inside acquire()
    normal_queued.set()

    t_priority = threading.Thread(target=priority_waiter)
    t_priority.start()
    time.sleep(0.05)                    # let the priority thread actually block inside acquire()

    release_holder.set()
    t_holder.join(timeout=5)
    t_normal.join(timeout=5)
    t_priority.join(timeout=5)

    assert order == ["priority", "normal"], (
        f"priority must be admitted first even though it queued later; got {order}")


def test_capacity_is_still_respected_when_priority_jumps_the_queue():
    """Jumping the queue must never mean exceeding capacity — priority changes WHO goes next, not
    how many go at once."""
    gate = _PriorityGate(capacity=2)
    in_use = 0
    peak = 0
    lock = threading.Lock()

    def worker(priority: bool):
        nonlocal in_use, peak
        with gate.acquire(priority=priority):
            with lock:
                in_use += 1
                peak = max(peak, in_use)
            time.sleep(0.02)
            with lock:
                in_use -= 1

    threads = [threading.Thread(target=worker, args=(i % 2 == 0,)) for i in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert peak <= 2
    assert in_use == 0


def test_a_slot_is_released_even_when_the_held_work_raises():
    """A retrieval that blows up must not leak its slot — every later request would eventually
    queue forever behind a gate that never frees up again."""
    gate = _PriorityGate(capacity=1)

    try:
        with gate.acquire():
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    acquired = []
    with gate.acquire():
        acquired.append(True)
    assert acquired == [True], "the gate stayed full after an exception inside it"


def test_a_waiter_interrupted_while_queued_does_not_leak_capacity(monkeypatch):
    """If my_turn.wait() itself is interrupted while a waiter is still queued (never granted), the
    Event must come out of the queue. Otherwise a LATER holder's _release() still pops it and
    .set()s it — nobody is listening any more — and increments `_in_use` for a grant that will
    never be matched by this waiter's own `finally: self._release()` (that code never runs), quietly
    stealing one unit of the gate's capacity forever."""
    gate = _PriorityGate(capacity=1)
    holder_ready = threading.Event()
    release_holder = threading.Event()

    def holder():
        with gate.acquire():
            holder_ready.set()
            release_holder.wait(timeout=5)

    t_holder = threading.Thread(target=holder)
    t_holder.start()
    holder_ready.wait(timeout=5)

    # Make the queued waiter's my_turn.wait() raise. threading.Thread.start() itself blocks the
    # CALLING thread on an internal Event.wait() until the new thread has actually started — that is
    # deterministically the FIRST Event.wait() call in this window, before the new thread ever
    # reaches gate.acquire(); my_turn.wait() is the second. (The holder's own release_holder.wait()
    # is already an in-progress call from earlier and is unaffected by re-patching the class now.)
    orig_wait = threading.Event.wait
    calls = {"n": 0}

    def flaky_wait(self, timeout=None):
        calls["n"] += 1
        if calls["n"] == 2:
            monkeypatch.setattr(threading.Event, "wait", orig_wait)   # one-shot
            raise RuntimeError("simulated interruption")
        return orig_wait(self, timeout)

    monkeypatch.setattr(threading.Event, "wait", flaky_wait)

    interrupted = []

    def waiter():
        try:
            with gate.acquire():
                pass  # pragma: no cover — must never be reached
        except RuntimeError:
            interrupted.append(True)

    t_waiter = threading.Thread(target=waiter)
    t_waiter.start()
    t_waiter.join(timeout=5)
    assert interrupted == [True], "the simulated interruption must propagate out of acquire()"
    assert not gate._priority_queue and not gate._normal_queue, (
        "the interrupted waiter's Event must not be left sitting in the queue")

    release_holder.set()
    t_holder.join(timeout=5)

    # The gate must still be at full, correct capacity afterward — no phantom grant leaked.
    assert gate._in_use == 0
    acquired = []
    with gate.acquire():
        acquired.append(True)
        assert gate._in_use == 1
    assert acquired == [True]


def test_two_priority_waiters_do_not_starve_each_other():
    """Priority beats normal, but priority-vs-priority is still first-come-first-served — nothing
    here should let one priority waiter block another indefinitely."""
    gate = _PriorityGate(capacity=1)
    order: list[int] = []
    order_lock = threading.Lock()
    holder_ready = threading.Event()
    release_holder = threading.Event()

    def holder():
        with gate.acquire():
            holder_ready.set()
            release_holder.wait(timeout=5)

    def priority_waiter(n: int, delay: float):
        holder_ready.wait(timeout=5)
        time.sleep(delay)               # stagger arrival so #1 queues strictly before #2
        with gate.acquire(priority=True):
            with order_lock:
                order.append(n)

    t_holder = threading.Thread(target=holder)
    t_holder.start()
    holder_ready.wait(timeout=5)

    t1 = threading.Thread(target=priority_waiter, args=(1, 0.0))
    t2 = threading.Thread(target=priority_waiter, args=(2, 0.05))
    t1.start()
    t2.start()
    time.sleep(0.15)                    # let both actually queue before releasing

    release_holder.set()
    t_holder.join(timeout=5)
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert order == [1, 2], f"expected arrival order among equals, got {order}"
