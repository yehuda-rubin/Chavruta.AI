"""LinkExpander.expand() must carry the full RankedHit field set (retrieval/link_expand.py).

It used to hand-roll its own payload->RankedHit mapping, a second copy of hybrid.py's own _to_hit —
and the copy was missing lang/text_he/text_en/license/version_title. A source that arrived via link
expansion (rather than a direct vector hit) then silently carried none of that: a Hebrew source
sheet had nothing to pick a language from, and CC-BY/CC-BY-SA attribution (required by the licence)
rendered blank. Fixed by reusing hybrid.py's _to_hit instead of a second, drifted copy.
"""
from __future__ import annotations

from types import SimpleNamespace

from chavruta.corpus.schema import Query
from chavruta.retrieval.link_expand import LinkExpander


class _FakeLinkGraph:
    def expand(self, refs, depth=1, work_ids=None):
        return ["Rashi_on_Genesis.1.1.1"]


class _FakeStore:
    def __init__(self, payload):
        self._payload = payload

    def fetch_by_refs(self, collection, refs, filters=None):
        return [SimpleNamespace(chunk_id="c1", score=0.0, payload=self._payload)]


def _make_expander(payload):
    store = _FakeStore(payload)
    profile = SimpleNamespace(collection="chavruta_commercial")
    return LinkExpander(store, _FakeLinkGraph(), profile, link_score=0.5)


def test_expand_carries_lang_and_bilingual_text_through():
    payload = {
        "ref": "Rashi_on_Genesis.1.1.1", "text": "[Rashi] Genesis.1.1.1\nHebrew text",
        "lang": "he", "text_he": "טקסט עברי", "text_en": "English text",
    }
    hits = _make_expander(payload).expand(["Genesis.1.1"], Query(text="x", expand_links=True))
    assert len(hits) == 1
    assert hits[0].lang == "he"
    assert hits[0].text_he == "טקסט עברי"
    assert hits[0].text_en == "English text"


def test_expand_carries_license_and_version_title_through():
    payload = {
        "ref": "Rashi_on_Genesis.1.1.1", "text": "…",
        "license": "CC-BY", "version_title": "Some Edition",
    }
    hits = _make_expander(payload).expand(["Genesis.1.1"], Query(text="x", expand_links=True))
    assert hits[0].license == "CC-BY"
    assert hits[0].version_title == "Some Edition"


def test_expand_still_uses_the_link_score_not_the_stores_own_score():
    """The one field that must NOT come from _to_hit unchanged: link-expanded hits rank below
    direct vector hits by design, regardless of whatever score the store attaches to the fetch."""
    payload = {"ref": "Rashi_on_Genesis.1.1.1", "text": "…"}
    expander = _make_expander(payload)
    hits = expander.expand(["Genesis.1.1"], Query(text="x", expand_links=True))
    assert hits[0].score == 0.5
