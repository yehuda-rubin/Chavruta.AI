"""Spec 009 Wave 2, T052/T053/T080/T081: a minor's audience (safety prompt block + content denylist)
reaches every prompt builder and every retrieval path, and adults / empty denylists change nothing.

Everything is synthetic: fake store, fake embedding, fake LLM, temporary SQLite. No network, no model.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

import app.db as db
import app.minors as minors
from chavruta.corpus import audience
from chavruta.corpus.audience import ADULT, AudienceScope, Denylist
from chavruta.corpus.schema import Intent, Query
from chavruta.generation import grounded
from chavruta.llm import agentic
from chavruta.pipeline.pipeline import ChavrutaPipeline
from chavruta.retrieval import denylist as dl
from chavruta.retrieval.hybrid import HybridRetriever
from chavruta.store.base import Hit

TODAY = date(2026, 10, 26)


# ── fakes ─────────────────────────────────────────────────────────────────────
def _payload(ref, work_id):
    return {"chunk_id": f"id:{ref}", "ref": ref, "work_id": work_id, "text": "טקסט", "unit_type": "source"}


CORPUS = [
    _payload("Genesis.1.1", "tanakh"),
    _payload("Rashi_on_Genesis.1.1.1", "tanakh"),
    _payload("Ramban_on_Genesis.1.1.1", "tanakh"),
    _payload("Bava_Metzia.3.1", "gemara"),
    _payload("Responsum_X.1.1", "shut"),
]


def _not_ids(filters):
    return set(((filters or {}).get("$not") or {}).get("work_id") or [])


class FakeStore:
    def __init__(self, corpus=CORPUS):
        self.corpus = corpus
        self.calls: list[tuple[str, dict | None, int | None]] = []

    def _apply(self, filters):
        return [p for p in self.corpus
                if p["work_id"] not in _not_ids(filters)
                and not (filters and "work_id" in filters and p["work_id"] not in filters["work_id"])]

    def search(self, name, query, top_k, filters=None):
        self.calls.append(("search", filters, top_k))
        return [Hit(chunk_id=p["chunk_id"], score=0.9, payload=p) for p in self._apply(filters)][:top_k]

    def dense_scores(self, name, dense, filters=None, top_k=30):
        self.calls.append(("dense_scores", filters, top_k))
        return {p["chunk_id"]: 0.9 for p in self._apply(filters)}

    def top_dense_score(self, name, dense, filters=None):
        self.calls.append(("top_dense_score", filters, None))
        return 0.9 if self._apply(filters) else 0.0

    def fetch_by_refs(self, name, refs, filters=None, *, limit=None):
        self.calls.append(("fetch_by_refs", filters, limit))
        return [Hit(chunk_id=p["chunk_id"], score=1.0, payload=p)
                for p in self._apply(filters) if p["ref"] in refs]


class FakeEmbedding:
    def embed_query(self, text):
        return SimpleNamespace(dense=[0.1], sparse={1: 1.0})


class FakeLLM:
    model_id = "fake"
    source_fetcher = None

    def __init__(self):
        self.jobs: list[str] = []

    def request(self, body, *, lang="he", token_budget=None):
        self.jobs.append(body)
        return "תשובה [S1]", []

    def generate(self, prompt, *, lang, max_tokens, temperature):
        self.jobs.append(prompt.system)
        return SimpleNamespace(text="תשובה [S1]", fetched_sources=[], finish_reason="stop")


PROFILE = SimpleNamespace(collection="c", hybrid=True, relevance_threshold=0.1, top_k=8,
                          llm_max_tokens=1000, llm_temperature=0.0)


@pytest.fixture
def pipe(monkeypatch):
    monkeypatch.setattr("chavruta.intents.llm_planner.distill_query", lambda text, **kw: text)
    store, llm = FakeStore(), FakeLLM()
    p = ChavrutaPipeline.from_backends(
        PROFILE, embedding=FakeEmbedding(), store=store, llm=llm,
        retriever=HybridRetriever(FakeEmbedding(), store, PROFILE))
    return p, store, llm


@pytest.fixture
def d(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "wiring.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    return db


def _scope(minor=True, work_ids=(), titles=()):
    return AudienceScope(minor=minor, deny=Denylist(frozenset(work_ids), frozenset(titles)))


# ── resolver ──────────────────────────────────────────────────────────────────
def test_resolver_splits_tiers_from_titles():
    r = dl.resolve_denylist([
        ("category", "shut"),                        # a tier slug
        ("category", "Kabbalah"),                    # a category that is exactly one tier
        ("category", "Responsa"),                    # ...under its catalogue name
        ("work", "Rashi on Genesis"),                # a book
        ("category", "Halakhah/Mishneh Torah"),      # a catalogue path -> many titles
        ("category", "no/such/category"),            # resolves to nothing: ignored, not an error
    ])
    assert r.work_ids == {"shut", "kabbalah"}
    assert "Rashi on Genesis" in r.titles
    assert any(t.startswith("Mishneh Torah") for t in r.titles)
    assert "Genesis" not in r.titles


def test_resolver_empty_is_falsy():
    assert not dl.resolve_denylist([])


def test_every_catalog_title_resolves_inside_its_own_category():
    # A title denied through its category must be recognised again from a stored ref of that book.
    r = dl.resolve_denylist([("category", "Halakhah/Mishneh Torah")])
    assert dl._title_of("Mishneh_Torah,_Sabbath.1.1") in r.titles


# ── effective denylist = school ∪ parents ────────────────────────────────────
def _make_minor(owner="kid"):
    return minors.set_age_once(owner, 2012, 5, today=TODAY)


def _org_with(member, rows):
    import app.orgs as orgs
    oid = orgs.create_org("teacher", "School", "free")
    now = db._now()
    with db._tx(db.get_conn()) as conn:
        conn.execute("INSERT INTO org_members (org_id, owner_id, role, invited_at, accepted_at) "
                     "VALUES (?,?,?,?,?)", (oid, member, "student", now, now))
        for kind, value in rows:
            conn.execute("INSERT INTO content_denylist VALUES ('org',?,?,?,?,?)",
                         (oid, kind, value, "teacher", now))
    return oid


def _parent_rows(child, rows, status="active"):
    now = db._now()
    with db._tx(db.get_conn()) as conn:
        conn.execute("INSERT INTO parent_links VALUES (?,?,?,?,?)", ("mom", child, status, now, now))
        for kind, value in rows:
            conn.execute("INSERT INTO content_denylist VALUES ('parent',?,?,?,?,?)",
                         (child, kind, value, "mom", now))


def test_effective_denylist_is_union_of_school_and_active_parent(d, monkeypatch):
    monkeypatch.setattr(minors, "_today", lambda today=None: TODAY)
    _make_minor()
    _org_with("kid", [("category", "shut")])
    _parent_rows("kid", [("work", "Rashi on Genesis")])
    sc = minors.audience_scope("kid", TODAY)
    assert sc.minor and sc.deny.work_ids == {"shut"} and sc.deny.titles == {"Rashi on Genesis"}


def test_revoked_parent_link_lifts_the_parents_rows(d):
    _make_minor()
    _parent_rows("kid", [("category", "shut")], status="revoked")
    assert minors.effective_denylist_rows("kid") == []


def test_adults_and_unknown_owners_get_the_default_scope(d):
    assert minors.audience_scope("nobody") is ADULT
    assert minors.audience_scope("local") is ADULT
    minors.set_age_once("grown", 1990, 1, today=TODAY)
    assert minors.audience_scope("grown", TODAY) is ADULT


# ── adult / empty: nothing changes ───────────────────────────────────────────
def test_default_scope_is_inert_everywhere():
    q = Query(text="x")
    assert dl.scoped_query(q) is q
    items = [object()]
    assert dl.drop_scoped(items) is items
    f = {"unit_type": "source"}
    assert dl.scoped_filters(f) is f and dl.scoped_filters(None) is None
    assert agentic.minor_system("SYS", "he") == "SYS"
    assert agentic.minor_job("JOB", "en") == "JOB"
    with audience.use(_scope(minor=True)):                       # a minor with NOTHING denied
        assert dl.scoped_query(q) is q and dl.scoped_filters(None) is None


def test_adult_retrieval_sends_no_denylist_and_matches_a_plain_run(pipe):
    p, store, llm = pipe
    p.ask(Query(text="שאלה", intent=Intent.QA))
    assert store.calls and all(not _not_ids(f) for _, f, _ in store.calls)
    assert all(grounded.MINOR_SAFETY_EN not in j and grounded.MINOR_SAFETY_HE not in j for j in llm.jobs)


# ── T052: prompts ─────────────────────────────────────────────────────────────
def test_minor_block_reaches_the_pipeline_job_and_the_system_prompt(pipe):
    p, store, llm = pipe
    with audience.use(_scope()):
        p.ask(Query(text="שאלה", intent=Intent.QA, lang="he"))
    assert any(grounded.MINOR_SAFETY_HE in j for j in llm.jobs)


def test_minor_system_covers_hand_built_jobs():
    with audience.use(_scope()):
        s = agentic.minor_system(agentic._REQUEST_SYSTEM, "en")
        job = agentic.minor_job("## QUESTION\nq", "he")
    assert s.endswith(grounded.MINOR_SAFETY_EN) and agentic._REQUEST_SYSTEM in s
    assert grounded.MINOR_SAFETY_HE in job and job.endswith("## QUESTION\nq")


def test_agentic_request_system_prompt_has_the_block_for_minors_only():
    seen = []

    class L:
        def generate(self, prompt, *, lang, max_tokens, temperature):
            seen.append(prompt.system)
            return SimpleNamespace(text="done", completion_tokens=1, prompt_tokens=1)
        source_fetcher = None

    agentic.agentic_request(L(), "job", lang="en")
    with audience.use(_scope()):
        agentic.agentic_request(L(), "job", lang="en")
    assert seen[0] == agentic._REQUEST_SYSTEM
    assert seen[1] == agentic._REQUEST_SYSTEM + grounded.MINOR_SAFETY_EN


def test_responsa_walkthrough_is_never_used_for_a_minor(pipe, monkeypatch):
    p, store, llm = pipe

    seen = {}
    real = grounded.build_lesson_walkthrough_prompt

    def spy(*a, **k):
        seen["shut"] = k.get("shut")
        return real(*a, **k)

    monkeypatch.setattr(grounded, "build_lesson_walkthrough_prompt", spy)
    with audience.use(_scope()):
        ans = p.ask(Query(text="שאלה", intent=Intent.HALACHA, lang="he"))
        # and the direct entry point, should anything call it
        p._lesson_answer(Query(text="שאלה", intent=Intent.HALACHA, lang="he"),
                         p.retriever.retrieve(Query(text="שאלה"), top_k=4), llm)
    assert ans.text
    assert seen.get("shut") in (None, False)                      # never True
    assert not any(grounded.SYSTEM_SHUT_WALKTHROUGH_HE[len(grounded.SYSTEM_BASE_HE):][:40] in j for j in llm.jobs)


def test_adult_responsa_still_uses_the_walkthrough(pipe, monkeypatch):
    p, store, llm = pipe
    seen = {}
    real = grounded.build_lesson_walkthrough_prompt
    monkeypatch.setattr(grounded, "build_lesson_walkthrough_prompt",
                        lambda *a, **k: (seen.setdefault("shut", k.get("shut")), real(*a, **k))[1])
    p._lesson_answer(Query(text="שאלה", intent=Intent.HALACHA, lang="he"),
                     p.retriever.retrieve(Query(text="שאלה"), top_k=4), llm)
    assert seen.get("shut") in (True, None)       # None only if the plan had no sections (plain prompt)


# ── T053: retrieval ───────────────────────────────────────────────────────────
def test_tier_denial_reaches_the_store_and_the_results(pipe):
    p, store, _ = pipe
    with audience.use(_scope(work_ids={"gemara"})):
        res = p.retriever.retrieve(Query(text="שאלה"), top_k=8)
    assert res.hits and "gemara" not in {h.work_id for h in res.hits}
    assert all("gemara" in _not_ids(f) for _, f, _ in store.calls)


def test_title_denial_overfetches_and_drops(pipe):
    p, store, _ = pipe
    base = store.calls
    p.retriever.retrieve(Query(text="שאלה"), top_k=8)
    plain_k = max(k for n, _, k in store.calls if n == "search")
    store.calls.clear()
    with audience.use(_scope(titles={"Rashi on Genesis"})):
        res = p.retriever.retrieve(Query(text="שאלה"), top_k=8)
    refs = {h.ref for h in res.hits}
    assert "Genesis.1.1" in refs and "Ramban_on_Genesis.1.1.1" in refs
    assert "Rashi_on_Genesis.1.1.1" not in refs
    assert max(k for n, _, k in store.calls if n == "search") > plain_k          # over-fetched
    del base


def test_title_denial_also_filters_anchors_and_named_refs(pipe):
    p, store, _ = pipe
    with audience.use(_scope(titles={"Genesis"})):
        res = p.retriever.retrieve(Query(text="x", named_refs=["Genesis.1.1"]), top_k=8)
    assert "Genesis.1.1" not in {h.ref for h in res.hits}
    assert "Genesis.1.1" not in res.anchor_refs


def test_agentic_need_sources_fetch_honours_the_denylist(pipe):
    p, store, llm = pipe
    assert callable(llm.source_fetcher)
    with audience.use(_scope(work_ids={"gemara"}, titles={"Rashi on Genesis"})):
        out = llm.source_fetcher(["שאלה אחרת"])
    refs = {s.ref for s in out}
    assert refs and not refs & {"Bava_Metzia.3.1", "Rashi_on_Genesis.1.1.1"}
    assert all("gemara" in _not_ids(f) for n, f, _ in store.calls)


def test_agentic_fetch_for_an_adult_is_unchanged(pipe):
    p, store, llm = pipe
    out = llm.source_fetcher(["שאלה אחרת"])
    assert "Bava_Metzia.3.1" in {s.ref for s in out}
    assert all(not _not_ids(f) for _, f, _ in store.calls)


def test_base_sources_for_refs_honours_tier_and_title(pipe):
    p, store, _ = pipe
    assert [h.ref for h in p.base_sources_for_refs(["Genesis.1.1"])] == ["Genesis.1.1"]
    with audience.use(_scope(work_ids={"tanakh"})):
        assert p.base_sources_for_refs(["Genesis.1.1"]) == []
    with audience.use(_scope(titles={"Genesis"})):
        assert p.base_sources_for_refs(["Genesis.1.1"]) == []


def test_link_expander_drops_denied_titles():
    from chavruta.retrieval.link_expand import LinkExpander

    class Graph:
        def __len__(self):
            return 1

        def expand(self, refs, depth=1, work_ids=None):
            return ["Rashi_on_Genesis.1.1.1", "Ramban_on_Genesis.1.1.1"]

    store = FakeStore()
    le = LinkExpander(store, Graph(), PROFILE)
    with audience.use(_scope(titles={"Rashi on Genesis"})):
        out = le.expand(["Genesis.1.1"], Query(text="x"))
    assert [h.ref for h in out] == ["Ramban_on_Genesis.1.1.1"]


def test_drop_scoped_uses_tier_map_and_title():
    cits = [SimpleNamespace(ref="Bava_Metzia.3.1"), SimpleNamespace(ref="Rashi_on_Genesis.1.1.1"),
            SimpleNamespace(ref="Genesis.1.1")]
    with audience.use(_scope(work_ids={"gemara"}, titles={"Rashi on Genesis"})):
        kept = dl.drop_scoped(cits, work_ids={"Bava_Metzia.3.1": "gemara"})
    assert [c.ref for c in kept] == ["Genesis.1.1"]


# ── api: the door that sets the scope ─────────────────────────────────────────
def test_run_query_sets_and_resets_the_scope(d, monkeypatch):
    import app.api as api

    _make_minor()
    _parent_rows("kid", [("category", "shut")])
    monkeypatch.setattr(minors, "_today", lambda today=None: TODAY)
    seen = []

    def impl(*a, **k):
        seen.append(audience.current())
        return api.QueryResponse(answer="ok", citations=[
            api.CitationOut(ref="Rashi_on_Genesis.1.1.1")], grounded=True, intent="qa", files=[])

    monkeypatch.setattr(api, "_run_query_impl", impl)
    monkeypatch.setattr(api, "_source_note_enabled", lambda o: False)
    res = api._run_query("שאלה", "he", "qa", [], owner_id="kid", llm=object())   # a minor always carries one (T050)
    assert seen[0].minor and seen[0].deny.work_ids == {"shut"}
    assert audience.current() is ADULT                              # reset afterwards
    api._run_query("שאלה", "he", "qa", [], owner_id="someone-else")
    assert seen[1] is ADULT
    assert [c.ref for c in res.citations] == ["Rashi_on_Genesis.1.1.1"]     # no title denied here


def test_scope_response_drops_denied_citations(monkeypatch):
    import app.api as api

    resp = api.QueryResponse(answer="a", citations=[api.CitationOut(ref="Rashi_on_Genesis.1.1.1"),
                                                      api.CitationOut(ref="Genesis.1.1")],
                             grounded=True, intent="qa", files=[])
    assert api._scope_response(resp) is resp and len(resp.citations) == 2           # adult: untouched
    with audience.use(_scope(titles={"Rashi on Genesis"})):
        api._scope_response(resp)
    assert [c.ref for c in resp.citations] == ["Genesis.1.1"]


def test_minor_gets_the_fixed_greeting_instead_of_the_classifiers_reply(d, monkeypatch):
    import app.api as api
    from chavruta.intents.llm_planner import DistillerResult

    monkeypatch.setattr(api, "classify_and_distill",
                        lambda *a, **k: DistillerResult(action="chitchat", answer="SECRET-LLM-TEXT", raw="HHH"))
    with audience.use(_scope()):
        r = api._run_query_impl("משהו", "he", "qa", [])
    assert "SECRET-LLM-TEXT" not in r.answer
    r2 = api._run_query_impl("משהו", "he", "qa", [])
    assert "SECRET-LLM-TEXT" in r2.answer


# ── T081: feedback expires on the minor schedule ─────────────────────────────
def test_minor_feedback_is_stamped_and_swept(d, monkeypatch):
    monkeypatch.setattr(minors, "_today", lambda today=None: TODAY)
    _make_minor("kid")
    minors.set_age_once("grown", 1990, 1, today=TODAY)
    db.submit_feedback("kid", "synthetic note")
    db.submit_feedback("grown", "synthetic note")
    db.submit_feedback("legacy", "synthetic note")
    rows = {r["owner_id"]: r["minor_until"] for r in
            db.get_conn().execute("SELECT owner_id, minor_until FROM feedback").fetchall()}
    assert rows["kid"] is not None and rows["grown"] is None and rows["legacy"] is None
    later = (datetime.now(UTC) + timedelta(days=minors.minor_retention_days() + 1)).isoformat()
    counts = db.delete_expired_minor_data(later, minors.minor_retention_days())
    assert counts["feedback"] == 1
    left = {r[0] for r in db.get_conn().execute("SELECT owner_id FROM feedback").fetchall()}
    assert left == {"grown", "legacy"}
    assert db.delete_expired_minor_data(later, 60)["feedback"] == 0


def test_feedback_migration_adds_the_column_to_a_schema_35_database(monkeypatch, tmp_path):
    import sqlite3

    path = tmp_path / "v35.db"
    monkeypatch.setattr(db, "DB_PATH", path)
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn().close()
    raw = sqlite3.connect(path)
    raw.execute("ALTER TABLE feedback DROP COLUMN minor_until")
    raw.execute("PRAGMA user_version = 35")
    raw.commit()
    raw.close()
    monkeypatch.setattr(db, "_conn", None)
    cols = {r[1] for r in db.get_conn().execute("PRAGMA table_info(feedback)")}
    assert "minor_until" in cols


# ── T080: the operator report copes with redacted rows ───────────────────────
def test_moderation_report_prints_redacted_minor_rows(d, monkeypatch, capsys):
    import importlib.util
    from pathlib import Path

    monkeypatch.setattr(minors, "_today", lambda today=None: TODAY)
    _make_minor("kid")
    sid = db.create_session("synthetic", mode="qa", owner_id="kid")
    mid = db.save_message(sid, "assistant", "synthetic answer text")
    db.report_message(mid, "kid", "wrong")
    adult_sid = db.create_session("synthetic", mode="qa", owner_id="grown")
    adult_mid = db.save_message(adult_sid, "assistant", "adult answer")
    db.report_message(adult_mid, "grown", "wrong")

    spec = importlib.util.spec_from_file_location(
        "moderation_report", Path(__file__).resolve().parents[2] / "scripts" / "moderation_report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rows = db.list_flagged_messages()
    assert any(r.get("minor") for r in rows) and any(not r.get("minor") for r in rows)
    for r in rows:
        mod._print_report(r)
    out = capsys.readouterr().out
    assert "minor (redacted)" in out and "kid" not in out
