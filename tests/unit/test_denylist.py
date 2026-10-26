"""Content denylist (spec 009 R10): every retrieval path must honour Query.deny_work_ids, and an empty
denylist must leave the store calls exactly as they were. No Qdrant server, no LLM, no network."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from chavruta.corpus.schema import Citation, Query
from chavruta.retrieval.denylist import drop_denied, work_ids_by_ref
from chavruta.retrieval.hybrid import HybridRetriever
from chavruta.retrieval.link_expand import LinkExpander
from chavruta.store.base import Hit

DENY = frozenset({"shut", "midrash"})
FOUNDATIONAL = ["tanakh", "mishnah", "gemara", "halacha", "midrash"]


def _payload(ref, work_id, text="טקסט"):
    return {"chunk_id": f"id:{ref}", "ref": ref, "work_id": work_id, "text": text}


CORPUS = [
    _payload("Genesis.1.1", "tanakh"),
    _payload("Rashi_on_Genesis.1.1.1", "tanakh"),
    _payload("Bava_Metzia.3.1", "gemara"),
    _payload("Shut_X.1.1", "shut"),
    _payload("Midrash_Y.1.1", "midrash"),
]


def _not_ids(filters):
    return set(((filters or {}).get("$not") or {}).get("work_id") or [])


class FakeStore:
    """In-memory store that applies `work_id` and `$not` filters the way QdrantStore does and logs
    every call so tests can assert on the exact filters sent."""

    def __init__(self, corpus=CORPUS):
        self.corpus = corpus
        self.calls: list[tuple[str, dict | None]] = []

    def _apply(self, filters):
        out = []
        for p in self.corpus:
            if filters and "work_id" in filters and p["work_id"] not in filters["work_id"]:
                continue
            if p["work_id"] in _not_ids(filters):
                continue
            out.append(p)
        return out

    def search(self, name, query, top_k, filters=None):
        self.calls.append(("search", filters))
        return [Hit(chunk_id=p["chunk_id"], score=0.9, payload=p) for p in self._apply(filters)][:top_k]

    def dense_scores(self, name, dense, filters=None, top_k=30):
        self.calls.append(("dense_scores", filters))
        return {p["chunk_id"]: 0.9 for p in self._apply(filters)}

    def top_dense_score(self, name, dense, filters=None):
        self.calls.append(("top_dense_score", filters))
        return 0.9 if self._apply(filters) else 0.0

    def fetch_by_refs(self, name, refs, filters=None, *, limit=None):
        self.calls.append(("fetch_by_refs", filters))
        return [Hit(chunk_id=p["chunk_id"], score=1.0, payload=p)
                for p in self._apply(filters) if p["ref"] in refs]


class FakeEmbedding:
    def embed_query(self, text):
        return SimpleNamespace(dense=[0.1], sparse={1: 1.0})

    def embed_batch(self, texts):
        return [self.embed_query(t) for t in texts]


PROFILE = SimpleNamespace(collection="c", hybrid=True, relevance_threshold=0.1)


def _retriever(store):
    return HybridRetriever(FakeEmbedding(), store, PROFILE)


def _ret(store, **qkw):
    return _retriever(store).retrieve(Query(text="שאלה על בראשית", **qkw), top_k=10)


def _all_store_calls_deny(store):
    assert store.calls
    for name, f in store.calls:
        assert DENY <= _not_ids(f), (name, f)


def test_default_query_has_empty_denylist():
    assert Query(text="x").deny_work_ids == frozenset()


def test_unscoped_retrieval_sends_deny_on_every_store_call():
    store = FakeStore()
    res = _ret(store, deny_work_ids=DENY)
    _all_store_calls_deny(store)
    assert res.hits and not {h.work_id for h in res.hits} & DENY


def test_unscoped_fallback_keeps_denylist():
    store = FakeStore()
    # scope matches nothing -> falls back to unscoped search, which must still deny
    res = _ret(store, work_ids=["nonexistent"], deny_work_ids=DENY)
    _all_store_calls_deny(store)
    assert any(h.work_id == "tanakh" for h in res.hits)
    assert not {h.work_id for h in res.hits} & DENY


def test_floors_tractate_and_quote_carry_denylist():
    store = FakeStore()
    q = Query(text="שאלה על בראשית", tractates=["Bava_Metzia"], deny_work_ids=DENY)
    _retriever(store).retrieve(q, top_k=10)
    _all_store_calls_deny(store)
    floors = [f for n, f in store.calls if n == "search" and f and "work_id" in f]
    assert floors  # base + foundational floors ran with work_id AND $not together
    for f in floors:
        assert _not_ids(f) == set(DENY)


def test_named_ref_anchoring_carries_denylist():
    store = FakeStore()
    q = Query(text="מה רשי אומר", named_refs=["Genesis.1.1"], commentator_ids=["rashi"],
              deny_work_ids=DENY)
    res = _retriever(store).retrieve(q, top_k=10)
    anchors = [f for n, f in store.calls if n == "fetch_by_refs"]
    assert anchors and all(_not_ids(f) == set(DENY) for f in anchors)
    assert "Genesis.1.1" in {h.ref for h in res.hits}


def test_scoped_search_merges_scope_and_denylist():
    store = FakeStore()
    q = Query(text="x", work_ids=["tanakh", "shut"], deny_work_ids=DENY)
    res = _retriever(store).retrieve(q, top_k=10)
    assert {h.work_id for h in res.hits} == {"tanakh"}
    first = store.calls[0][1]
    assert first["work_id"] == ["tanakh", "shut"] and _not_ids(first) == set(DENY)


def test_link_expansion_carries_denylist_and_post_filters():
    class Graph:
        def expand(self, refs, depth=1, work_ids=None):
            return ["Rashi_on_Genesis.1.1.1", "Shut_X.1.1"]

    store = FakeStore()
    hits = LinkExpander(store, Graph(), PROFILE).expand(
        ["Genesis.1.1"], Query(text="x", expand_links=True, deny_work_ids=DENY))
    assert [h.ref for h in hits] == ["Rashi_on_Genesis.1.1.1"]
    assert _not_ids(store.calls[-1][1]) == set(DENY)


def test_link_expansion_post_filter_catches_a_store_that_ignores_filters():
    class LeakyStore(FakeStore):
        def fetch_by_refs(self, name, refs, filters=None, *, limit=None):
            return [Hit(chunk_id=p["chunk_id"], score=1.0, payload=p)
                    for p in self.corpus if p["ref"] in refs]

    class Graph:
        def expand(self, refs, depth=1, work_ids=None):
            return ["Shut_X.1.1", "Rashi_on_Genesis.1.1.1"]

    hits = LinkExpander(LeakyStore(), Graph(), PROFILE).expand(
        ["Genesis.1.1"], Query(text="x", expand_links=True, deny_work_ids=DENY))
    assert [h.work_id for h in hits] == ["tanakh"]


def test_retriever_post_filter_catches_a_store_that_ignores_filters():
    class LeakyStore(FakeStore):
        def _apply(self, filters):
            return list(self.corpus)

    res = _ret(LeakyStore(), deny_work_ids=DENY)
    assert res.hits and not {h.work_id for h in res.hits} & DENY


def test_empty_denylist_sends_exactly_todays_calls():
    store = FakeStore()
    q = Query(text="שאלה על בראשית", tractates=["Bava_Metzia"], named_refs=["Genesis.1.1"])
    _retriever(store).retrieve(q, top_k=10)
    for name, f in store.calls:
        assert "$not" not in (f or {}), (name, f)
    assert store.calls[0] == ("search", None)           # unscoped main search is filterless
    assert any(f == {"work_id": FOUNDATIONAL} for _, f in store.calls)
    assert ("fetch_by_refs", None) in store.calls        # anchoring: no work scope, no filter


def test_empty_denylist_unfiltered_floors_get_no_filters_kwarg():
    seen = []

    class Strict(FakeStore):
        def search(self, name, query, top_k, **kw):
            seen.append(kw)
            return super().search(name, query, top_k, **kw)

    _retriever(Strict()).retrieve(Query(text="שאלה על בראשית", tractates=["Bava_Metzia"]), top_k=10)
    assert {} in seen  # tractate / quote floors: no `filters` kwarg at all, exactly as before


def test_empty_denylist_link_expansion_unchanged():
    class Graph:
        def expand(self, refs, depth=1, work_ids=None):
            return ["Rashi_on_Genesis.1.1.1"]

    store = FakeStore()
    LinkExpander(store, Graph(), PROFILE).expand(["Genesis.1.1"], Query(text="x", expand_links=True))
    assert store.calls[-1] == ("fetch_by_refs", None)


# -- drop_denied ---------------------------------------------------------------

def test_drop_denied_on_dicts_and_objects():
    items = [{"work_id": "shut", "ref": "a"}, {"work_id": "tanakh", "ref": "b"},
             SimpleNamespace(work_id="midrash", ref="c"), SimpleNamespace(work_id="gemara", ref="d")]
    kept = drop_denied(items, DENY)
    assert [i["ref"] if isinstance(i, dict) else i.ref for i in kept] == ["b", "d"]


def test_drop_denied_empty_denylist_returns_all():
    items = [{"work_id": "shut"}]
    assert drop_denied(items, frozenset()) == items


def test_drop_denied_citations_via_ref_resolver():
    hits = [SimpleNamespace(ref="Shut_X.1.1", work_id="shut"),
            SimpleNamespace(ref="Genesis.1.1", work_id="tanakh")]
    m = work_ids_by_ref(hits)
    cites = [Citation(chunk_id="1", ref="Shut_X.1.1", deep_link=""),
             Citation(chunk_id="2", ref="Genesis.1.1", deep_link="")]
    kept = drop_denied(cites, DENY, work_of=lambda c: m.get(c.ref))
    assert [c.ref for c in kept] == ["Genesis.1.1"]


@pytest.mark.parametrize("keep_unknown,expected", [(True, 1), (False, 0)])
def test_drop_denied_unknown_work(keep_unknown, expected):
    c = Citation(chunk_id="1", ref="Zzz.1", deep_link="")
    assert len(drop_denied([c], DENY, keep_unknown=keep_unknown)) == expected


# -- QdrantStore._build_filter (qdrant_client models only, no server) -----------

def test_build_filter_not_key():
    pytest.importorskip("qdrant_client")
    from chavruta.store.qdrant_store import QdrantStore

    s = QdrantStore()
    f = s._build_filter({"work_id": ["tanakh"], "$not": {"work_id": ["shut", "midrash"]}})
    assert [c.key for c in f.must] == ["work_id"]
    assert [c.key for c in f.must_not] == ["work_id"]
    assert f.must_not[0].match.any == ["shut", "midrash"]
    only = s._build_filter({"$not": {"work_id": ["shut"]}})
    assert not only.must and len(only.must_not) == 1


def test_build_filter_unchanged_without_not():
    pytest.importorskip("qdrant_client")
    from chavruta.store.qdrant_store import QdrantStore

    f = QdrantStore()._build_filter({"work_id": ["tanakh"]})
    assert f.must_not is None and len(f.must) == 1
    assert QdrantStore()._build_filter(None) is None


def test_fetch_by_refs_keeps_must_not():
    pytest.importorskip("qdrant_client")
    from chavruta.store.qdrant_store import QdrantStore

    captured = {}

    class Client:
        def scroll(self, **kw):
            captured.update(kw)
            return [], None

    s = QdrantStore()
    s._client = Client()
    s.fetch_by_refs("c", ["Genesis.1.1"], filters={"$not": {"work_id": ["shut"]}})
    flt = captured["scroll_filter"]
    assert [c.key for c in flt.must_not] == ["work_id"] and len(flt.must) == 1
