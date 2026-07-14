"""Regression gate for the Tier 0–2 audit fixes (2026-07).

Every test here pins a specific bug that was fixed, so a future refactor can't silently
re-introduce it. All are deterministic — pure heuristics + registry, no Qdrant and no LLM.
Grouped by the layer they exercise: intent router, corpus registry, and the api lesson
helpers (audience / clarify-answer detection).
"""

from __future__ import annotations

import pytest

from chavruta.corpus.registry import default_registry
from chavruta.corpus.schema import Intent, Query
from chavruta.intents.router import (
    Router,
    detect_commentators,
    detect_intent,
    detect_requested_works,
)


# ── Tier 0-C: whole-word alias matching (COMMENTATOR / WORK) ──────────────────────
# Bug: a bare substring test fired 'רשי' inside 'מפרשים' / 'שרשי', and 'משנה' inside
# 'משנה תורה' / 'משנה ברורה'. Fixed with word-boundary matching + a one-hop prefix class
# that deliberately EXCLUDES ש (so 'שרשי' can't reach 'רשי').

@pytest.mark.parametrize("text", [
    "מה שרשי המילה הזאת",        # שרשי (roots) must NOT match rashi
    "לפי כל המפרשים על הפסוק",   # מפרשים (commentators) contains 'רשי' — must NOT match
    "פרשת השבוע",                # פרש… — must NOT match
])
def test_rashi_not_falsely_detected(text):
    assert "rashi" not in detect_commentators(text)


@pytest.mark.parametrize("text", [
    'מה אומר רש"י כאן',           # bare
    "מה אומר רשי כאן",           # no gershayim
    'ולרש"י יש פירוש אחר',        # two stacked one-letter prefixes ו+ל
    'לפי הרש"י',                  # ה prefix
])
def test_rashi_detected_with_prefixes(text):
    assert "rashi" in detect_commentators(text)


def test_mishneh_torah_not_tagged_as_mishnah():
    """'משנה תורה' is the Rambam's code, not the Mishnah — the bare 'משנה' work must drop."""
    works = detect_requested_works("מה פוסק הרמב\"ם במשנה תורה")
    assert "mishneh_torah" in works
    assert "mishnah" not in works


def test_mishnah_berurah_not_tagged_as_mishnah():
    works = detect_requested_works("מה כותב המשנה ברורה על הלכות שבת")
    assert "mishnah_berurah" in works
    assert "mishnah" not in works


def test_plain_mishnah_still_detected():
    assert "mishnah" in detect_requested_works("מה אומרת המשנה על זמן קריאת שמע")


def test_masechet_does_not_force_mishnah_work():
    """'מסכת' was removed from the Mishnah aliases — a Talmud tractate is not the Mishnah."""
    assert "mishnah" not in detect_requested_works("מה הדין במסכת בבא מציעא")


# ── Tier 0-C2: registry knows the loaded categories + their aliases ───────────────
# Bug: the registry only knew 'tanakh', so has('talmud') was False and honest-refusal logic
# for genuinely-unloaded works couldn't tell a loaded corpus from a missing one.

@pytest.mark.parametrize("cat", [
    "tanakh", "mishnah", "talmud_bavli", "halacha", "responsa", "midrash", "kabbalah",
])
def test_registry_has_loaded_categories(cat):
    assert default_registry().has(cat)


@pytest.mark.parametrize("alias,canonical", [
    ("talmud", "talmud_bavli"),
    ("shulchan_aruch", "halacha"),
    ("mishneh_torah", "halacha"),
    ("zohar", "kabbalah"),
])
def test_registry_resolves_aliases(alias, canonical):
    r = default_registry()
    assert r.has(alias) and r.has(canonical)


def test_registry_rejects_unloaded_work():
    """A genuinely out-of-corpus modern work must stay unknown → honest-refusal path fires."""
    assert not default_registry().has("modern_torah")


# ── Tier 0: halacha intent tightened ─────────────────────────────────────────────
# Bug: bare 'מותר'/'אסור'/'הלכה' over-triggered the heavy responsa machine on ordinary
# narrative questions. Now requires an interrogative / pesak framing.

@pytest.mark.parametrize("text", [
    "מה אסור לפרעה לעשות במצרים",     # narrative 'אסור', not a halachic query
    "מדוע מותר לעם ישראל לצאת",        # narrative 'מותר'
    "מה ההלכות שלמד משה בסיני",        # mentions הלכות, not a ruling question
])
def test_narrative_not_routed_to_halacha(text):
    assert detect_intent(text, 0) is not Intent.HALACHA


@pytest.mark.parametrize("text", [
    "האם מותר לאכול בשר עוף בחלב",
    "האם אסור לטלטל מוקצה בשבת",
    "מה הדין בהלכות מוקצה",
    "מהי ההלכה למעשה בברכת שהחיינו",
])
def test_genuine_ruling_routed_to_halacha(text):
    assert detect_intent(text, 0) is Intent.HALACHA


# ── Router-level: 'shut'/responsa question still surfaces the responsa work ───────

def test_router_responsa_work_detected():
    q = Router().route(Query(text='מה כתוב בשו"ת על השאלה הזאת'))
    assert q.requested_works and "responsa" in q.requested_works


# ── api lesson helpers: audience / grade-band / clarify-answer detection ──────────
# These live in app/api.py; importing it is cheap (no eager pipeline/embedder build).
# Bug set: (a) the plural 'כיתות ד–ו' clarify-answer was read as a fresh topic because the
# grade range was consumed before the range-strip; (b) English grade/school phrasing wasn't
# detected; (c) a real topic must NOT be mistaken for a clarify-answer.

api = pytest.importorskip("app.api")


@pytest.mark.parametrize("text", [
    "לכיתות ד–ו",          # plural + range — the exact case that regressed
    "כיתה ה",
    "ד",                    # a lone grade letter
    "grades 4-6",
    "high school",
])
def test_clarify_answer_recognised(text):
    assert api._is_clarify_answer(text) is True


@pytest.mark.parametrize("text", [
    "הלכות שבת",            # a real topic, not a clarify-answer
    "שניים אוחזין בטלית",
    "the laws of Shabbat",
    "the dispute between Rashi and Ramban",
])
def test_real_topic_not_a_clarify_answer(text):
    assert api._is_clarify_answer(text) is False


@pytest.mark.parametrize("text,band", [
    ("שיעור לכיתה ב", "a-c"),
    ("שיעור לכיתה ה", "d-f"),
    ("שיעור לכיתה ח", "g-i"),
    ("שיעור לכיתה יא", "j-l"),
])
def test_grade_band_detection(text, band):
    assert api._detect_band(text) == band


@pytest.mark.parametrize("text", [
    "prepare a lesson for 5th grade",
    "a shiur for high school students",
    "בית ספר יסודי",
])
def test_school_audience_detected(text):
    assert api._detect_school(text)


# ── Fix (2026-07-13): strip model multilingual bleed (CJK / Cyrillic / Vietnamese) from output,
# keeping Hebrew glued to a foreign char; legit Hebrew + English are untouched.
@pytest.mark.parametrize("raw,expected", [
    ("בזדון违反 שבת", "בזדון שבת"),                          # CJK glued to Hebrew → Hebrew kept
    ("לא требуется הסכמה", "לא הסכמה"),                       # whole Cyrillic word removed
    ("נבראו השמים והארץ", "נבראו השמים והארץ"),              # clean Hebrew untouched
    ("Rashi explains thus", "Rashi explains thus"),          # English untouched
])
def test_strip_foreign_removes_bleed(raw, expected):
    assert api._strip_foreign(raw) == expected


# ── Tier0 (2026-07 audit): chavruta weak-retrieval must use the dense-cosine gate, not the RRF score ──
# Bug: `_run_chavruta` compared the raw hit .score (an RRF fusion value ~0.03 in hybrid mode) to a 0.6
# cosine threshold, so "retrieval is weak" fired on EVERY hybrid turn and nudged the chavruta to stall.

from types import SimpleNamespace  # noqa: E402

from chavruta.retrieval.base import RankedHit, RetrievalResult  # noqa: E402


def _fake_pipeline(result, captured):
    class _Retriever:
        def retrieve(self, rq, top_k):
            return result

    class _LLM:
        source_fetcher = None

        def request(self, body_md, *, lang="he"):
            captured["job"] = body_md
            return ("תשובה מעוגנת [S1]" if result.hits else "רגע, תכוון אותי"), []

    return SimpleNamespace(retriever=_Retriever(), llm=_LLM(), _resolve_query=lambda q: q)


def test_chavruta_not_weak_on_good_hybrid_retrieval(monkeypatch):
    captured = {}
    hit = RankedHit(chunk_id="a", ref="Bava Metzia.2a", text="שנים אוחזין בטלית", score=0.03)  # RRF scale
    result = RetrievalResult(hits=[hit], is_empty=False)
    monkeypatch.setattr(api, "_get_pipeline", lambda: _fake_pipeline(result, captured))
    resp = api._run_chavruta("נלמד את סוגיית שניים אוחזין", "he", history=[])
    assert "RETRIEVAL CONFIDENCE IS LOW" not in captured["job"]   # good retrieval ⇒ NOT weak
    assert resp.intent == "chavruta"


def test_chavruta_weak_only_when_retrieval_empty(monkeypatch):
    captured = {}
    result = RetrievalResult(hits=[], is_empty=True)          # nothing cleared the relevance bar
    monkeypatch.setattr(api, "_get_pipeline", lambda: _fake_pipeline(result, captured))
    api._run_chavruta("שאלה על משהו שלא בקורפוס", "he", history=[])
    assert "RETRIEVAL CONFIDENCE IS LOW" in captured["job"]    # genuinely thin ⇒ weak banner shown


# ── Tier0 (2026-07 audit): lesson primary-source floor — router↔corpus ref canonicalisation ──────
# The corpus stores Tanakh verses as 'Genesis 1.1' (space after the book) but the router emits
# 'Genesis.1.1' (dots), so an exact-ref base-source lookup silently found nothing → the base pasuk
# never led the lesson. _canon_corpus_ref bridges the gap WITHOUT corrupting already-spaced refs.

from chavruta.pipeline.pipeline import ChavrutaPipeline  # noqa: E402


@pytest.mark.parametrize("ref,expected", [
    ("Genesis.1.1", "Genesis 1.1"),          # verse-level router ref → corpus form
    ("Exodus.20", "Exodus 20"),              # chapter-level
    ("I Samuel.3.10", "I Samuel 3.10"),      # book name with a space
    ("Song of Songs.1.1", "Song of Songs 1.1"),
    ("Mishnah Bava Metzia 1.1", "Mishnah Bava Metzia 1.1"),  # already corpus form — MUST NOT corrupt
    ("Berakhot 2a", "Berakhot 2a"),          # no dot-before-digit at the book boundary — unchanged
])
def test_canon_corpus_ref(ref, expected):
    assert ChavrutaPipeline._canon_corpus_ref(ref) == expected


def test_with_ref_variants_covers_dot_space_and_chapter_opening():
    from chavruta.corpus.refs import with_ref_variants
    # verse-level: dot + corpus-space forms so anchoring matches whichever the store uses
    assert with_ref_variants(["Genesis.1.1"]) == ["Genesis.1.1", "Genesis 1.1"]
    # chapter-level: also the opening verse, since base texts are stored per-verse
    assert with_ref_variants(["Exodus.20"]) == ["Exodus.20", "Exodus 20", "Exodus 20.1"]
    # already-spaced ref (Mishnah) isn't corrupted or duplicated
    assert with_ref_variants(["Mishnah Sukkah 3.5"]) == ["Mishnah Sukkah 3.5"]


# ── Tier1 (2026-07): Talmud daf amud form → corpus amud-linear ref (N = 2·daf − 1/2·daf) ──────────
@pytest.mark.parametrize("ref,corpus", [
    ("Sanhedrin.23a", "Sanhedrin 45.1"),     # 23a → 2·23−1 = 45  (perek 3 'זה בורר')
    ("Bava Metzia.2a", "Bava Metzia 3.1"),   # 2a  → 3           ('שנים אוחזין')
    ("Berakhot.2b", "Berakhot 4.1"),         # 2b  → 2·2 = 4
])
def test_amud_to_corpus_in_variants(ref, corpus):
    from chavruta.corpus.refs import with_ref_variants
    assert corpus in with_ref_variants([ref])


# ── Tier1 (2026-07): perek-ordinal → opening-daf resolution (Sefaria-built index) ────────────────
# The opening SEGMENT matters: a perek usually opens mid-amud (Berakhot 3 = 17b:12 → 'Berakhot 34.12',
# NOT '.1' which is the previous perek's aggadic tail). Exact refs, verified against the live corpus.
@pytest.mark.parametrize("text,expected", [
    ("אני רוצה ללמוד את הדף הראשון בפרק שלישי בסנהדרין", "Sanhedrin 45.1"),  # the motivating example
    ("פרק שלישי בברכות", "Berakhot 34.12"),   # opens mid-amud (17b:12) — 'מי שמתו', not the '.1' tail
    ("פרק ג' בבבא מציעא", "Bava Metzia 66.7"),  # 'המפקיד'
])
def test_perek_ordinal_resolves(text, expected):
    from chavruta.intents.landmarks import resolve_landmarks
    assert expected in resolve_landmarks(text)


@pytest.mark.parametrize("text", ["פרק זה בשבת", "בפרק זה במסכת שבת", "פרק הוא בגיטין"])
def test_perek_demonstrative_not_gematria(text):
    """'פרק זה' = 'THIS chapter' — gematria('זה')=12 must NOT fabricate a perek number/daf."""
    from chavruta.intents.landmarks import resolve_landmarks
    assert not any(r.split()[0] in ("Shabbat", "Gittin") and r[-2:] != "2a" for r in resolve_landmarks(text))


def test_amud_to_corpus_ignores_volume_numbered_works():
    """Talmud amud→corpus must not fire on volume-numbered refs like the Zohar ('Zohar 1.15a')."""
    from chavruta.corpus.refs import with_ref_variants
    assert with_ref_variants(["Zohar.1.15a"]) == ["Zohar.1.15a", "Zohar 1.15a"]   # no bogus 'Zohar 1 29.1'


# ── Tier1 (2026-07 round-3/4): English landmark resolution — word-boundary, no substring collisions ──
@pytest.mark.parametrize("text,expected", [
    ("What does the Torah say about the binding of Isaac?", "Genesis.22"),
    ("Explain the Shema", "Deuteronomy.6.4"),
    ("the ten commandments", "Exodus.20"),
    ("love your neighbor as yourself", "Leviticus.19.18"),
])
def test_english_landmarks(text, expected):
    from chavruta.intents.landmarks import resolve_landmarks
    assert expected in resolve_landmarks(text)


@pytest.mark.parametrize("text", [
    "Who was the prophet Shemaiah?",          # 'shema' must NOT match inside 'Shemaiah'
    "In the beginning of tractate Bava Kamma",  # discourse phrase, not Genesis 1:1
    "the flooding of the field",              # not the Genesis flood
])
def test_english_landmarks_no_false_positive(text):
    from chavruta.intents.landmarks import resolve_landmarks
    assert resolve_landmarks(text) == []


# ── Tier1 (2026-07): END-TO-END anchoring through the retriever with the real corpus ref-format ──
# The corpus stores base verses SPACE-form ('Genesis 1.3') but the router emits DOTTED named_refs
# ('Genesis.1.3'). This exercises with_ref_variants THROUGH HybridRetriever.retrieve — it fails if the
# anchoring path stops canonicalising (the exact regression that measured Tanakh recall at ~13%).
def test_anchoring_resolves_dotted_named_ref_against_space_form_corpus():
    from chavruta.retrieval.hybrid import HybridRetriever

    class _Emb:
        def embed_query(self, text):
            return SimpleNamespace(dense=[0.1, 0.2], sparse={1: 0.5})

    class _Store:
        def search(self, name, q, top_k, filters=None):        # main + floors surface only commentary
            if filters:
                return []
            return [Hit(chunk_id="c1", score=0.05,
                        payload={"chunk_id": "c1", "ref": "Rashi on Genesis 1.3", "text": "פירוש",
                                 "commentator_id": "rashi", "unit_type": "commentary"})]

        def fetch_by_refs(self, name, refs, filters=None):     # base verse stored SPACE-form only
            if "Genesis 1.3" in refs:
                return [Hit(chunk_id="g13", score=1.0,
                            payload={"chunk_id": "g13", "ref": "Genesis 1.3", "text": "ויאמר אלהים יהי אור",
                                     "unit_type": "source", "work_id": "tanakh"})]
            return []

        def dense_scores(self, name, dense, filters=None, top_k=30):
            return {}

    prof = SimpleNamespace(hybrid=True, collection="c", relevance_threshold=0.5, rerank=False)
    q = Query(text="מה נאמר בפסוק?")
    q.named_refs = ["Genesis.1.3"]                              # dotted, as the router emits
    res = HybridRetriever(_Emb(), _Store(), prof).retrieve(q, top_k=8)
    anchored = [h for h in res.hits if h.ref == "Genesis 1.3"]
    assert anchored and anchored[0].score >= 1.0               # the base pasuk anchored despite dot↔space


# ── Tier1 (2026-07): the api _run_query graceful-error wrapper (degrade, not 500; keep real 4xx) ──
def test_run_query_degrades_on_backend_exception(monkeypatch):
    monkeypatch.setattr(api, "_run_query_impl",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("qdrant down")))
    resp = api._run_query("שאלה", "he", "qa", [])
    assert resp.grounded is False and resp.intent == "qa" and "שגיאה" in resp.answer


def test_run_query_propagates_http_exception(monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setattr(api, "_run_query_impl",
                        lambda *a, **k: (_ for _ in ()).throw(HTTPException(status_code=422, detail="x")))
    with pytest.raises(HTTPException):
        api._run_query("שאלה", "he", "nonsense-intent", [])


def test_base_sources_for_refs_canonicalises_dedups_and_scores(monkeypatch):
    """base_sources_for_refs must look up the canonical ref, return RankedHits at score 1.0, and dedup."""
    calls = []

    class _Store:
        def fetch_by_refs(self, name, refs, filters=None):
            calls.append((refs, filters))
            # emulate the corpus: the base verse exists under the SPACE form only
            if refs == ["Genesis 1.1"]:
                return [SimpleNamespace(chunk_id="g11", score=1.0,
                                        payload={"ref": "Genesis 1.1", "text": "בראשית",
                                                 "unit_type": "source", "work_id": "tanakh"})]
            return []

    pipe = SimpleNamespace(store=_Store(), profile=SimpleNamespace(collection="chavruta"),
                           _canon_corpus_ref=ChavrutaPipeline._canon_corpus_ref)
    out = ChavrutaPipeline.base_sources_for_refs(pipe, ["Genesis.1.1", "Genesis.1.1", "Nonexistent.9.9"])
    assert [h.ref for h in out] == ["Genesis 1.1"]            # canonicalised, deduped, missing dropped
    assert out[0].score == 1.0                                # a resolved base source is a certain anchor
    assert (["Genesis 1.1"], {"unit_type": "source"}) in calls  # queried the corpus form + source filter


# ── Feature (2026-07-13): on EMPTY retrieval, QA gives the model a chance to pull its own sources via
# the agentic ===NEED_SOURCES=== loop before honestly giving up (Principle I is preserved — a self-fetch
# that still yields nothing falls back to the no-source answer).
def _selffetch_pipeline(llm):
    from chavruta.config.profile import Profile
    from chavruta.retrieval.base import RetrievalResult

    class _Empty:
        def retrieve(self, q, top_k):
            return RetrievalResult(hits=[], anchor_refs=[], is_empty=True)

    prof = Profile(name="cloud", collection="c", top_k=5, relevance_threshold=0.0)
    return ChavrutaPipeline.from_backends(prof, embedding=None, store=None, llm=llm,
                                          retriever=_Empty(), router=SimpleNamespace(route=lambda q: q))


def test_qa_empty_retrieval_selffetches_grounded():
    from chavruta.corpus.schema import Query, Intent
    from chavruta.llm.base import SourceBlock
    src = SourceBlock(marker="", ref="Yoma 8.1", commentator_id=None, text="יום הכיפורים אסור באכילה")

    class _LLM:
        profile = "cloud"; model_id = "fake"
        source_fetcher = staticmethod(lambda qs: [src])

        def request(self, body_md, *, lang="he"):
            assert "===NEED_SOURCES===" in body_md            # the job invited a self-fetch
            return ("איסור אכילה ביום כיפור נלמד מעינוי [S1]", [src])

        def generate(self, *a, **k):
            raise AssertionError("generate must NOT be called when retrieval is empty — self-fetch first")

    ans = _selffetch_pipeline(_LLM()).ask(Query(text="מקור לאיסור אכילה ביום כיפור", lang="he", intent=Intent.QA))
    assert ans.grounded is True and ans.no_source is False
    assert any(c.ref == "Yoma 8.1" for c in ans.citations)    # cited the source it fetched itself


def test_qa_empty_retrieval_selffetch_fails_is_honest():
    from chavruta.corpus.schema import Query, Intent

    class _LLM:
        profile = "cloud"; model_id = "fake"
        source_fetcher = staticmethod(lambda qs: [])

        def request(self, body_md, *, lang="he"):
            # the loop's no-fetch degrade sentinel — nothing relevant could be pulled
            return ("לא הצלחתי להשיג מקורות מתאימים דרך הראג. נסה לנסח מחדש או לציין מקור מדויק.", [])

    ans = _selffetch_pipeline(_LLM()).ask(Query(text="שאלה על משהו שאינו בקורפוס", lang="he", intent=Intent.QA))
    assert ans.grounded is False and ans.citations == []      # honest no-source, never invented


# ── Tier0 (2026-07 audit): per-hit relevance floor prunes dense semantic noise, keeps lexical hits ──
# Bug: the honesty gate was all-or-nothing (top hit only), so off-topic-but-similar sources (Kilayim
# for a Shabbat question) shipped to the model. The floor drops a hit ONLY if dense retrieval itself
# surfaced it below threshold — sparse/lexical-driven hits (absent from the dense map) are kept.

from chavruta.store.base import Hit  # noqa: E402


def test_per_hit_dense_floor_prunes_noise_keeps_lexical():
    from chavruta.retrieval.hybrid import HybridRetriever

    class _Emb:
        def embed_query(self, text):
            return SimpleNamespace(dense=[0.1, 0.2], sparse={1: 0.5})

    class _Store:
        def search(self, name, q, top_k, filters=None):
            if filters and "work_id" in filters:            # foundational-floor probe → nothing extra
                return []
            return [
                Hit(chunk_id="good", score=0.05, payload={"chunk_id": "good", "ref": "Berakhot 2a", "text": "t"}),
                Hit(chunk_id="noise", score=0.049, payload={"chunk_id": "noise", "ref": "Mishnah Kilayim 8.1", "text": "t"}),
                Hit(chunk_id="lex", score=0.048, payload={"chunk_id": "lex", "ref": "Shabbat 12a", "text": "t"}),
            ]

        def dense_scores(self, name, dense, filters=None, top_k=30):
            return {"good": 0.70, "noise": 0.42}             # 'lex' absent → sparse-driven, must survive

    prof = SimpleNamespace(hybrid=True, collection="c", relevance_threshold=0.55, rerank=False)
    res = HybridRetriever(_Emb(), _Store(), prof).retrieve(Query(text="הלכות שבת"), top_k=5)
    refs = [h.ref for h in res.hits]
    assert "Berakhot 2a" in refs                              # on-topic dense hit kept
    assert "Shabbat 12a" in refs                              # sparse/lexical hit (not in dense map) kept
    assert "Mishnah Kilayim 8.1" not in refs                  # dense-surfaced sub-threshold noise pruned
    assert not res.is_empty                                   # top dense cosine 0.70 ≥ threshold


# ── Fix (2026-07-13): a WRONG work/commentator scope (e.g. a hallucinated/mis-resolved named_ref
# pinning the query to the wrong tractate) must NOT collapse retrieval to zero — retrieve falls back
# to an UNSCOPED semantic search so the topically-relevant sources still surface.
def test_wrong_scope_falls_back_to_unscoped_semantic():
    from chavruta.retrieval.hybrid import HybridRetriever

    class _Emb:
        def embed_query(self, text):
            return SimpleNamespace(dense=[0.1, 0.2], sparse={1: 0.5})

    class _Store:
        def search(self, name, q, top_k, filters=None):
            if filters and "work_id" in filters:            # ANY scoped search (wrong work / floors) → empty
                return []
            return [Hit(chunk_id="s1", score=0.05,          # unscoped fallback finds the real source
                        payload={"chunk_id": "s1", "ref": "Sanhedrin 3.1", "text": "t", "work_id": "talmud_bavli"})]

        def dense_scores(self, name, dense, filters=None, top_k=30):
            return {"s1": 0.72}

        def fetch_by_refs(self, name, refs, filters=None):
            return []

        def top_dense_score(self, name, dense, filters=None):
            return 0.72

    prof = SimpleNamespace(hybrid=True, collection="c", relevance_threshold=0.55, rerank=False)
    q = Query(text="דיני ממונות בשלושה")
    q.work_ids = ["bava_metzia"]                             # WRONG scope (hallucinated named_ref)
    res = HybridRetriever(_Emb(), _Store(), prof).retrieve(q, top_k=8)
    assert not res.is_empty
    assert any(h.ref == "Sanhedrin 3.1" for h in res.hits)   # unscoped fallback surfaced the real source


# ── Tier0 (2026-07 audit): the agentic ===NEED_SOURCES=== loop is now backend-agnostic ───────────
# It was a private method on BridgeLLM only; hoisted to chavruta.llm.agentic so cloud/local get it too.

from chavruta.llm.agentic import run_agentic_loop, parse_need_sources  # noqa: E402
from chavruta.llm.base import SourceBlock  # noqa: E402


def test_parse_need_sources_variants():
    assert parse_need_sources("===NEED_SOURCES===\nסנהדרין כג\nזה בורר") == ["סנהדרין כג", "זה בורר"]
    assert parse_need_sources("a normal answer with [S1]") == []
    assert parse_need_sources("x\n=== NEED SOURCES ===\n- one\n- two\n===END===") == ["one", "two"]


def test_agentic_loop_fetches_then_answers():
    """The loop: model asks for sources → fetcher supplies them → model answers. Fetched sources are
    returned in order and the appended job carried them with continued [S#] markers."""
    seen_jobs = []
    replies = iter(["===NEED_SOURCES===\nזה בורר לו אחד", "התשובה המלאה [S2]"])

    def send(job_md):
        seen_jobs.append(job_md)
        return next(replies)

    fetched_block = [SourceBlock(marker="", ref="Mishnah Sanhedrin 3.1", commentator_id=None, text="זה בורר")]
    text, fetched = run_agentic_loop(send, "## SOURCES\n### [S1] X\nbody", lambda qs: fetched_block, "he")
    assert text == "התשובה המלאה [S2]"
    assert [s.ref for s in fetched] == ["Mishnah Sanhedrin 3.1"]
    assert "ADDITIONAL SOURCES" in seen_jobs[1] and "[S2]" in seen_jobs[1]   # round 2 carried the fetch


def test_agentic_loop_no_fetcher_returns_answer_directly():
    text, fetched = run_agentic_loop(lambda j: "תשובה [S1]", "job", None, "he")
    assert text == "תשובה [S1]" and fetched == []


def test_agentic_loop_forces_answer_on_final_round():
    """Fix (2026-07-13): a model that keeps replying ===NEED_SOURCES=== every round must be FORCED to
    write a real answer on the last round (via the appended FINAL instruction), not dead-end in a
    'couldn't get sources' degrade — observed with strong cloud models on source-scattered topics."""
    from chavruta.llm.agentic import is_degrade_message
    block = [SourceBlock(marker="", ref="Sanhedrin 3.1", commentator_id=None, text="t")]

    def send(job):                       # obeys only once the final-round instruction is present
        if "הוראה אחרונה" in job or "FINAL INSTRUCTION" in job:
            return "השיעור המלא על דיני ממונות בשלושה [S1]"
        return "===NEED_SOURCES===\nעוד מקור על סנהדרין"

    text, fetched = run_agentic_loop(send, "## SOURCES\n### [S1] X\nbody", lambda qs: block, "he")
    assert text == "השיעור המלא על דיני ממונות בשלושה [S1]"
    assert not is_degrade_message(text)      # a real lesson, NOT the degrade message


def test_is_degrade_message_detects_sentinels_and_empty():
    from chavruta.llm.agentic import is_degrade_message, DEGRADE_MESSAGES
    assert is_degrade_message("")                                   # empty ⇒ not a real answer
    assert is_degrade_message("   ")
    for m in DEGRADE_MESSAGES:
        assert is_degrade_message(m)                                # each timeout/no-fetch sentinel
    assert not is_degrade_message("שיעור מלא על שניים אוחזין [S1]")  # a real lesson is NOT a degrade


def test_agentic_request_degrades_when_generate_raises():
    """Re-audit fix A: a completion backend raises on any API error/timeout; the request path must
    degrade gracefully (like the bridge's None) instead of propagating a 500."""
    from chavruta.llm.agentic import agentic_request

    class _Boom:
        source_fetcher = None

        def generate(self, prompt, *, lang, max_tokens, temperature):
            raise RuntimeError("Nebius 429 rate limit")

    text, fetched = agentic_request(_Boom(), "job", lang="he")
    assert "לא התקבלה" in text and fetched == []          # graceful timeout message, no exception


# ── Tier1 (2026-07 round-5 audit): marker-space poisoning — the append offset must count only source
# headers, never a [S#] token that appears in the user's question / history / a source body. Otherwise
# the fetched-source numbering shifts and the caller's positional `hits + fetched` mapping misattributes
# (or drops) the model's cited source.
def test_max_marker_counts_only_source_headers():
    from chavruta.llm.agentic import max_marker
    job = ("## QUESTION\nהסבר את מה שראיתי ב[S30]\n\n## SOURCES\n"
           "### [S1] Genesis 1.1\nבראשית\n### [S2] Rashi on Genesis 1.1\nפירוש")
    assert max_marker(job) == 2                # the two ### [S#] headers — NOT the inline [S30] in the question
    assert max_marker("nothing here") == 0


def test_agentic_append_offset_immune_to_user_text_marker():
    replies = iter(["===NEED_SOURCES===\nזה בורר", "answer [S2]"])
    seen = []

    def send(job):
        seen.append(job)
        return next(replies)

    job = "## QUESTION\nמה המקור ל[S30]?\n\n## SOURCES\n### [S1] X\nbody"
    block = [SourceBlock(marker="", ref="Mishnah Sanhedrin 3.1", commentator_id=None, text="זה בורר")]
    _, fetched = run_agentic_loop(send, job, lambda qs: block, "he")
    assert "### [S2] Mishnah Sanhedrin 3.1" in seen[1]   # continues from the ONE real header, not [S31]
    assert "[S31]" not in seen[1]


# ── Tier1 (2026-07 round-5 audit): dense-only honesty gate must read the RAW top-1 dense cosine, not
# hits[0].score — the foundational floor boosts by +0.05, which could otherwise lift an off-topic hit
# over the threshold and dishonestly flip is_empty to False.
def test_dense_only_gate_ignores_floor_boost():
    from chavruta.retrieval.hybrid import HybridRetriever

    class _Emb:
        def embed_query(self, text):
            return SimpleNamespace(dense=[0.1, 0.2], sparse={})        # no sparse ⇒ dense-only mode

    class _Store:
        def search(self, name, q, top_k, filters=None):
            if filters and "work_id" in filters:
                if "unit_type" in filters:
                    return []                                          # base-source floor: nothing
                return [Hit(chunk_id="found", score=0.48,              # foundational floor hit → +0.05
                            payload={"chunk_id": "found", "ref": "Genesis 1.1", "text": "t", "work_id": "tanakh"})]
            return [Hit(chunk_id="main", score=0.40,
                        payload={"chunk_id": "main", "ref": "Off Topic 1", "text": "t"})]

        def dense_scores(self, name, dense, filters=None, top_k=30):
            return {}

        def top_dense_score(self, name, dense, filters=None):
            return 0.40                                                # true top cosine, below threshold

    prof = SimpleNamespace(hybrid=False, collection="c", relevance_threshold=0.5, rerank=False)
    res = HybridRetriever(_Emb(), _Store(), prof).retrieve(Query(text="off topic"), top_k=5)
    assert res.is_empty          # floor hit boosted 0.48→0.53 (≥thr) but true cosine 0.40 < 0.50 ⇒ honest empty


# ── Feature (2026-07-13): sticky chat mode — a chat stays in the intent chosen on its first turn.
# session_query must IGNORE any intent the client sends on later turns and replay the session's locked
# mode (legacy sessions with mode=None fall back to the per-request intent).
def test_session_query_locks_mode_to_first_turn(monkeypatch):
    from app.api import QueryRequest
    captured = {}

    monkeypatch.setattr(api.db, "get_messages", lambda sid: [{"role": "user", "text": "q1"}])
    monkeypatch.setattr(api.db, "save_message", lambda *a, **k: 1)
    monkeypatch.setattr(api.db, "get_session_mode", lambda sid: "chavruta")   # locked on turn 1

    def _fake_run_query(question, lang, intent, history, **kw):
        captured["intent"] = intent
        return api.QueryResponse(answer="ok", citations=[], grounded=True, intent=intent, files=[])

    monkeypatch.setattr(api, "_run_query", _fake_run_query)
    # client tries to switch to 'lesson' mid-chat — must be ignored in favour of the locked 'chavruta'
    api.session_query("sid-1", QueryRequest(question="follow-up", lang="he", intent="lesson"))
    assert captured["intent"] == "chavruta"


def test_session_query_legacy_session_falls_back_to_request_intent(monkeypatch):
    from app.api import QueryRequest
    captured = {}
    monkeypatch.setattr(api.db, "get_messages", lambda sid: [{"role": "user", "text": "q1"}])
    monkeypatch.setattr(api.db, "save_message", lambda *a, **k: 1)
    monkeypatch.setattr(api.db, "get_session_mode", lambda sid: None)         # legacy: no locked mode

    def _fake_run_query(question, lang, intent, history, **kw):
        captured["intent"] = intent
        return api.QueryResponse(answer="ok", citations=[], grounded=True, intent=intent, files=[])

    monkeypatch.setattr(api, "_run_query", _fake_run_query)
    api.session_query("sid-legacy", QueryRequest(question="q", lang="he", intent="qa"))
    assert captured["intent"] == "qa"
