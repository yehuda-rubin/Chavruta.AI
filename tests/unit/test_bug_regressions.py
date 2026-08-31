"""Regression gate for the Tier 0–2 audit fixes (2026-07).

Every test here pins a specific bug that was fixed, so a future refactor can't silently
re-introduce it. All are deterministic — pure heuristics + registry, no Qdrant and no LLM.
Grouped by the layer they exercise: intent router, corpus registry, and the api lesson
helpers (audience / clarify-answer detection).
"""

from __future__ import annotations

import threading
import time

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
    "tanakh", "mishnah", "gemara", "yerushalmi", "halacha", "shut", "midrash", "kabbalah",
])
def test_registry_has_loaded_categories(cat):
    assert default_registry().has(cat)


@pytest.mark.parametrize("alias,canonical", [
    ("talmud", "gemara"),
    ("responsa", "shut"),
    ("shulchan_aruch", "halacha"),
    ("mishneh_torah", "halacha"),
    ("zohar", "kabbalah"),
])
def test_registry_resolves_aliases(alias, canonical):
    r = default_registry()
    assert r.has(alias) and r.has(canonical)


# Fix (2026-08-12): these two tests used to assert 'talmud_bavli' and 'responsa' as CATEGORY names,
# which is what the code believed — and what the corpus never carried. The live collection tags
# those tiers `gemara` (516,854 points) and `shut` (96,493), so every filter built on the old names
# matched 0 of 2,403,599 points, silently. The tests were locking the mismatch in place.
#
# The category keys are matched against Qdrant payloads, so they are DATA, not naming taste. This
# guard pins them to the values counted in the live collection; if an ingest ever renames a tier,
# it fails here rather than in a filter that quietly returns nothing.
_CORPUS_WORK_IDS = {
    "tanakh", "mishnah", "gemara", "yerushalmi", "tosefta", "midrash", "halacha", "shut",
    "kabbalah", "chasidut", "musar", "jewish_thought", "liturgy", "reference", "second_temple",
}


def test_registry_categories_are_real_corpus_work_ids():
    from chavruta.corpus.registry import _LOADED_CATEGORIES

    unknown = set(_LOADED_CATEGORIES) - _CORPUS_WORK_IDS
    assert not unknown, f"registry names no corpus tier holds: {sorted(unknown)}"


def test_foundational_floor_targets_real_tiers_including_the_gemara():
    """The floors reserve result slots for the foundational works. Filtering them on a work_id the
    corpus doesn't use means the floor reserves nothing — which is what happened to the Gemara, the
    largest tier in the corpus."""
    from chavruta.retrieval.hybrid import _FOUNDATIONAL_WORKS

    assert "gemara" in _FOUNDATIONAL_WORKS
    assert not set(_FOUNDATIONAL_WORKS) - _CORPUS_WORK_IDS


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


# ── Bug (reported 2026-08-25): English lesson-building loop ──────────────────────
# User builds a lesson in English, answers "who is it for" with a natural plural phrasing
# ("grades 4-6", "6th graders") instead of the singular "5th grade" the old regex expected.
# _detect_school used \bgrade\b (singular, exact word) so it silently failed to recognize these
# real replies as school-audience text; _resolve_audience then returned aud=None again, and
# _run_lesson re-asked the IDENTICAL "who is the lesson for" question — the loop the user
# experienced as "it keeps asking me the same thing." Hebrew was unaffected: כית(?:ה|ת|ות) already
# covers both singular and plural forms. Fixed by widening \bgrade\b to \bgrades?\b|\bgraders?\b.
@pytest.mark.parametrize("text", [
    "grades 4-6",
    "for grades 7-9",
    "6th graders",
    "a class of 10th graders",
])
def test_school_audience_detected_for_plural_english_phrasing(text):
    assert api._detect_school(text)


def test_english_grade_loop_is_actually_fixed_not_just_reworded():
    """End-to-end: a realistic English reply to the (rewritten) clarify question must resolve
    BOTH audience and grade band in one turn, so _run_lesson does not ask again."""
    aud, band = api._resolve_audience("grades 4-6", [], "", "")
    assert (aud, band) == ("school", "d-f")

    aud, band = api._resolve_audience("6th graders", [], "", "")
    assert (aud, band) == ("school", "d-f")


@pytest.mark.parametrize("text,expected_band", [
    ("6th grade", "d-f"),               # matches the new question's own example
    ("middle school", "g-i"),           # matches the new question's own example
    ("grades 7-9", "g-i"),              # matches the new question's own example
])
def test_new_english_clarify_examples_resolve(text, expected_band):
    """The rewritten English question (app/api.py ~1160-1172) suggests these exact example
    replies — 'e.g. "6th grade," "middle school," or "grades 7-9"'. Each one must actually
    resolve through _resolve_audience, or the reworded question would just move the loop
    rather than fix it."""
    aud, band = api._resolve_audience(text, [], "", "")
    assert aud == "school"
    assert band == expected_band


# ── Fix (2026-07-13, generalized 2026-08-02): strip model multilingual bleed from output, keeping
# Hebrew glued to a foreign char; legit Hebrew + English + common typography are untouched. Arabic
# turned up live on 2026-08-02 — rather than adding it to an ever-growing enumerated list of scripts
# (CJK, Cyrillic, Vietnamese diacritics, now Arabic), _FOREIGN_CHAR_RE was flipped to an ALLOWLIST
# (ASCII + Hebrew + a few "smart" punctuation marks), so any OTHER script is caught automatically.
@pytest.mark.parametrize("raw,expected", [
    ("בזדון违反 שבת", "בזדון שבת"),                          # CJK glued to Hebrew → Hebrew kept
    ("לא требуется הסכמה", "לא הסכמה"),                       # whole Cyrillic word removed
    ("הטקסט מכיל ערבית: هذا نص عربي באמצע", "הטקסט מכיל ערבית: באמצע"),   # Arabic — the live 2026-08-02 report
    ("נבראו השמים והארץ", "נבראו השמים והארץ"),              # clean Hebrew untouched
    ("Rashi explains thus", "Rashi explains thus"),          # English untouched (handled elsewhere)
    ("משפט עם — מקף ארוך ו\"מרכאות חכמות\" ו… שלוש נקודות",   # "smart" typography (em dash, curly
     "משפט עם — מקף ארוך ו\"מרכאות חכמות\" ו… שלוש נקודות"),  # quotes, ellipsis) must survive the allowlist
])
def test_strip_foreign_removes_bleed(raw, expected):
    assert api._strip_foreign(raw) == expected


# ── Fix (2026-08-02): a real user reported the model injecting a stray English aside into an
# otherwise-Hebrew answer, e.g. '...שמתוארת במשנה (Bava Metzia 3:1), עוסקת...' — reproduced live
# against production. Strip a parenthetical made up ENTIRELY of Latin letters/digits/punctuation
# when the answer is Hebrew (he=True); leave it in English answers, leave numeric-only asides like
# '(1)' alone (no Latin letter), and leave a mixed Hebrew+Latin aside alone.
@pytest.mark.parametrize("raw,expected", [
    ("הסוגיה (Bava Metzia 3:1) עוסקת בטלית", "הסוגיה עוסקת בטלית"),
    ("ראה שיטה זו (Rashi) לעיל", "ראה שיטה זו לעיל"),
    ("סעיף (1) קובע", "סעיף (1) קובע"),                       # numeric-only aside untouched
    ("עיין (רש\"י) שם", "עיין (רש\"י) שם"),                    # Hebrew-only aside untouched
    ("עיין (עיין Rashi) שם", "עיין (עיין Rashi) שם"),          # mixed aside untouched
])
def test_strip_markers_removes_english_aside_in_hebrew_answers(raw, expected):
    assert api._strip_markers(raw, he=True) == expected


def test_strip_markers_keeps_english_aside_in_english_answers():
    raw = "The sugya (Bava Metzia 3:1) discusses a garment"
    assert api._strip_markers(raw, he=False) == raw


# ── Fix (2026-08-02): a real user reported a SECOND bleed pattern in the same live test — a bare
# English word mid-sentence with no parentheses at all ("שהוא אינו מ CLAIM על פחות מחצי"), which the
# parenthetical strip above cannot catch (and mechanically deleting the word would leave broken
# Hebrew grammar). _fix_bleeding_sentences asks the model to rewrite ONLY the offending sentence.
from types import SimpleNamespace  # noqa: E402


class _FakeLLM:
    """Records every prompt it's asked to rewrite; replies with a scripted (or default) rewrite.
    `reply`/`raises` apply to every call; pass `replies`/`raises_on` (lists, one entry per successive
    call) to script a DIFFERENT outcome each time — e.g. a failed or still-bleeding first attempt
    followed by a clean retry."""

    def __init__(self, reply="תשובה נקייה", raises=False, replies=None, raises_on=None):
        self.reply = reply
        self.raises = raises
        self.replies = replies
        self.raises_on = raises_on or []
        self.calls: list[str] = []

    def generate(self, prompt, *, lang, max_tokens, temperature):
        n = len(self.calls)
        self.calls.append(prompt.question)
        if self.raises_on[n] if n < len(self.raises_on) else self.raises:
            raise RuntimeError("model unavailable")
        text = self.replies[n] if self.replies is not None and n < len(self.replies) else self.reply
        return SimpleNamespace(text=text)


def test_fix_bleeding_sentences_rewrites_only_the_offending_sentence():
    # The trailing '. ' is captured as a SEPARATOR by the splitter, not part of the sentence text —
    # the scripted reply below (like a real rewrite) is just the sentence body, no trailing period.
    llm = _FakeLLM(reply="הוא אינו טוען על פחות מחצי")
    text = "משפט ראשון תקין. הוא אינו מ CLAIM על פחות מחצי. משפט שלישי תקין."
    out = api._fix_bleeding_sentences(text, True, llm)
    assert out == "משפט ראשון תקין. הוא אינו טוען על פחות מחצי. משפט שלישי תקין."
    assert len(llm.calls) == 1
    assert "CLAIM" in llm.calls[0]                # the fed sentence is exactly the bleeding one


def test_fix_bleeding_sentences_noop_when_not_hebrew():
    llm = _FakeLLM()
    text = "The answer includes a CLAIM about the source."
    assert api._fix_bleeding_sentences(text, False, llm) == text
    assert llm.calls == []


def test_fix_bleeding_sentences_noop_on_clean_hebrew():
    llm = _FakeLLM()
    text = "תשובה נקייה לגמרי בעברית, בלי שום מילה זרה."
    assert api._fix_bleeding_sentences(text, True, llm) == text
    assert llm.calls == []                        # never calls the model when there's nothing to fix


def test_fix_bleeding_sentences_keeps_original_on_llm_failure():
    llm = _FakeLLM(raises=True)
    text = "משפט עם מילה CLAIM בעייתית."
    assert api._fix_bleeding_sentences(text, True, llm) == text   # unchanged, not crashed


def test_fix_bleeding_sentences_caps_the_number_of_fixes():
    llm = _FakeLLM(reply="תוקן")
    # One more bleeding sentence than _MAX_BLEED_FIXES, whatever that's currently set to — the
    # LAST word is the one expected to survive uncapped, regardless of the cap's exact value.
    words = [f"W{i}" for i in range(api._MAX_BLEED_FIXES + 1)]
    text = " ".join(f"משפט {w} מספר {i}." for i, w in enumerate(words, 1))
    out = api._fix_bleeding_sentences(text, True, llm)
    assert len(llm.calls) == api._MAX_BLEED_FIXES
    assert words[-1] in out                        # the extra bleeding sentence was left untouched


# ── Fix (2026-08-12): the cap rose to 20 (a long lesson/responsa answer bleeds in far more than the
# 8 sentences the previous cap allowed, and every sentence over the cap reached the user in broken
# Hebrew). Raising it alone would have put up to 20 sentences x 2 attempts = 40 model calls IN SERIES
# in front of the user, so the rewrites now run concurrently — they are independent by construction,
# each seeing one sentence and nothing else.
class _ConcurrencyProbeLLM:
    """Records the high-water mark of simultaneously in-flight rewrite calls."""

    def __init__(self, serial_only=False):
        if serial_only:
            self.serial_only = True
        self._lock = threading.Lock()
        self.in_flight = 0
        self.max_in_flight = 0
        self.calls: list[str] = []

    def generate(self, prompt, *, lang, max_tokens, temperature):
        with self._lock:
            self.calls.append(prompt.question)
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        time.sleep(0.05)          # long enough that serial execution could not overlap
        with self._lock:
            self.in_flight -= 1
        return SimpleNamespace(text="תוקן")


def _text_with_bleeding_sentences(n: int) -> str:
    # Zero-padded so no marker is a substring of another ("W2" would match inside "W20").
    return " ".join(f"משפט W{i:03d} מספר {i}." for i in range(n))


def test_fix_bleeding_sentences_rewrites_concurrently():
    llm = _ConcurrencyProbeLLM()
    out = api._fix_bleeding_sentences(_text_with_bleeding_sentences(8), True, llm)
    assert len(llm.calls) == 8
    assert llm.max_in_flight > 1                   # the whole point: not one-at-a-time
    assert not api._has_bleed(out)


def test_fix_bleeding_sentences_stays_serial_for_a_serial_only_backend():
    # The bridge answers through a single job file — overlapping calls would put two jobs in front
    # of one reader with no way to match answers back to jobs.
    llm = _ConcurrencyProbeLLM(serial_only=True)
    api._fix_bleeding_sentences(_text_with_bleeding_sentences(6), True, llm)
    assert llm.calls and llm.max_in_flight == 1


def test_bridge_backend_declares_itself_serial_only():
    from chavruta.llm.bridge import BridgeLLM

    assert BridgeLLM.serial_only is True


def test_fix_bleeding_sentences_caps_the_FIRST_n_sentences_regardless_of_scheduling():
    # With the rewrites running in a pool, "which sentences get fixed" must not depend on which
    # thread finishes first: the cap is applied to the SELECTION, in document order.
    llm = _FakeLLM(reply="תוקן")
    text = _text_with_bleeding_sentences(api._MAX_BLEED_FIXES + 3)
    out = api._fix_bleeding_sentences(text, True, llm)
    for i in range(api._MAX_BLEED_FIXES):
        assert f"W{i:03d}" not in out               # the first N were rewritten
    for i in range(api._MAX_BLEED_FIXES, api._MAX_BLEED_FIXES + 3):
        assert f"W{i:03d}" in out                   # the tail was left untouched


# Fix (caught live 2026-08-04): a bleeding sentence reached a real user unfixed
# ("...שNERואה כמשתחוה..."). The first cut of _fix_bleeding_sentences accepted whatever the rewrite
# call returned as long as it was non-empty — never checking whether it had actually removed the
# Latin text — so a call that raised, or one that succeeded but came back still bleeding, was a dead
# end after a single try. It now retries once on either failure mode before giving up.
def test_fix_bleeding_sentences_retries_when_the_first_rewrite_still_bleeds():
    llm = _FakeLLM(replies=["still has CLAIM in it", "הוא אינו טוען דבר"])
    text = "משפט עם מילה CLAIM בעייתית."
    out = api._fix_bleeding_sentences(text, True, llm)
    assert out == "הוא אינו טוען דבר"
    assert len(llm.calls) == 2


def test_fix_bleeding_sentences_retries_after_a_call_failure():
    llm = _FakeLLM(raises_on=[True, False], reply="הוא אינו טוען דבר")
    text = "משפט עם מילה CLAIM בעייתית."
    out = api._fix_bleeding_sentences(text, True, llm)
    assert out == "הוא אינו טוען דבר"
    assert len(llm.calls) == 2


def test_fix_bleeding_sentences_keeps_original_when_both_attempts_still_bleed():
    llm = _FakeLLM(reply="still has CLAIM in it")   # every attempt comes back still bleeding
    text = "משפט עם מילה CLAIM בעייתית."
    assert api._fix_bleeding_sentences(text, True, llm) == text
    assert len(llm.calls) == 2                      # both attempts used, neither accepted


# Fix (caught live 2026-08-05): "...שה cה הזו..." (a single stray Latin letter mid-word) survived
# unfixed — the old trigger (_LATIN_WORD_RE) only fired on a RUN of 2+ Latin letters, so one bare
# letter slipped through both this mechanism and the blind foreign-char stripper (which allows all
# ASCII). _has_bleed checks CHARACTERS instead: anything that isn't Hebrew, ASCII-non-letter, or
# the app's own typography — catching a single Latin letter, and any other foreign script too.
def test_has_bleed_catches_a_single_stray_latin_letter():
    assert api._has_bleed("יש חשש שה cה הזו תיראה") is True


def test_has_bleed_catches_a_foreign_script_not_just_latin():
    assert api._has_bleed("בזדון违反") is True          # Chinese
    assert api._has_bleed("это требуется") is True      # Cyrillic


def test_has_bleed_false_on_clean_hebrew_with_markers():
    # [S1] contains a Latin "S" — must NOT itself count as bleed, or every cited sentence would
    # trigger a pointless rewrite call.
    assert api._has_bleed("זהו משפט נקי [S1] לגמרי.") is False
    assert api._has_bleed("שני מקורות [S1, S5] כאן.") is False


def test_fix_bleeding_sentences_fixes_a_single_stray_letter():
    llm = _FakeLLM(reply="יש חשש שהתנועה הזו תיראה")
    text = "יש חשש שה cה הזו תיראה כאילו הוא משתחווה לה."
    out = api._fix_bleeding_sentences(text, True, llm)
    assert "c" not in out
    assert len(llm.calls) == 1


# ── Naming the specific offending word(s), not just "this sentence bleeds" (2026-08-20) ───────
# Detection was never the gap — _has_bleed correctly flags real production answers every time it
# was checked. The two-attempt REWRITE kept failing identically on a foreign term the model doesn't
# recognize as a violation on its own: 'chez' survived two same-shape attempts (2026-08-14), and
# 'qualify' plus a transliterated work title ('MASKIL LEDAVID') reached a real user unfixed
# (2026-08-20) — even though the work's own Hebrew name was sitting right there in the sources
# block. _rewrite_bleeding_sentence now tells the model exactly which word(s) are the problem.
def test_bleed_words_extracts_a_single_english_word():
    assert api._bleed_words("ולכן, רק אכילה ושתיה qualify, כי הן היחידים") == ["qualify"]


def test_bleed_words_keeps_a_multi_word_transliteration_together():
    """'MASKIL LEDAVID' must come back as ONE phrase — splitting it in two would produce a rewrite
    instruction naming two meaningless fragments instead of the actual work title."""
    assert api._bleed_words("הMASKIL LEDAVID מסביר את משמעות") == ["MASKIL LEDAVID"]


def test_bleed_words_ignores_a_real_marker():
    assert api._bleed_words("משפט נקי [S1] עם [S2, S3] בלבד") == []


def test_bleed_words_is_empty_on_clean_hebrew():
    assert api._bleed_words("זהו משפט עברי תקין לחלוטין.") == []


class _SystemCapturingLLM:
    """Like _FakeLLM, but also records the SYSTEM prompt each call was given — needed to check the
    rewrite call actually names the offending word(s), not just to check its final answer."""

    def __init__(self, reply: str):
        self.reply = reply
        self.systems: list[str] = []

    def generate(self, prompt, *, lang, max_tokens, temperature):
        self.systems.append(prompt.system)
        return SimpleNamespace(text=self.reply)


def test_the_rewrite_call_is_told_the_specific_offending_word():
    llm = _SystemCapturingLLM(reply="רק אכילה ושתיה כשירות, כי הן היחידים")
    api._rewrite_bleeding_sentence("רק אכילה ושתיה qualify, כי הן היחידים", llm)

    assert llm.systems, "the rewrite call was never made"
    assert "qualify" in llm.systems[0], (
        "the offending word must be named explicitly in the system prompt, not left for the model "
        "to notice on its own — that is exactly where the un-targeted version kept failing")


def test_a_clean_rewrite_is_still_accepted_when_the_word_is_named():
    llm = _SystemCapturingLLM(reply="הMASKIL LEDAVID הפך למשכיל לדוד")   # deliberately still bleeding
    llm.reply = "משכיל לדוד מסביר את משמעות"                             # actually clean this time
    out = api._rewrite_bleeding_sentence("המשכיל לדוד MASKIL LEDAVID מסביר את משמעות", llm)
    assert out == "משכיל לדוד מסביר את משמעות"


# Fix (caught live 2026-08-04): the model quoted a source containing a Hebrew abbreviation gershayim
# (בר"ה) and emitted a literal backslash before it (בר\"ה) — as if escaping the quote the way a
# JSON/code string would. A bare backslash has no legitimate use in this app's output.
@pytest.mark.parametrize("raw,expected", [
    ('נאמר: "הנוהגים לשחות בר\\"ה וי\\"ה כשאומרים".', 'נאמר: "הנוהגים לשחות בר"ה וי"ה כשאומרים".'),
    ("תשובה נקייה לגמרי בלי בק סלאש.", "תשובה נקייה לגמרי בלי בק סלאש."),   # untouched when absent
])
def test_strip_markers_drops_a_leaked_escape_backslash_before_a_quote(raw, expected):
    assert api._strip_markers(raw, he=True) == expected


# ── Fix (2026-08-12, caught live): the model uses a marker as the NOUN, not as a trailing footnote
# — "ב[S2] יש דיון" ("in [source 2] there is a discussion") — so deleting only the marker stranded
# the preposition that introduced it. Real users saw "כי באמת, ב יש דיון" and "הבא נבדוק את: שם
# נאמר". Same trap the English-word path avoids by rewriting instead of deleting; markers were
# getting blind deletion. All four cases below are reproduced verbatim from production output.
@pytest.mark.parametrize("raw,expected", [
    ("כי באמת, ב[S2] יש דיון מעניין.", "כי באמת, יש דיון מעניין."),
    ("הבא נבדוק את [S3]: שם נאמר...", "הבא נבדוק: שם נאמר..."),
    ("כמו שמציע החסיד נתן אדלער ב[S4], או...", "כמו שמציע החסיד נתן אדלער, או..."),
    # Same failure shape via the all-Latin parenthetical stripper rather than the marker regex.
    ("ראינו זאת ב(Chatam Sofer on Sukkah 41a).", "ראינו זאת."),
])
def test_strip_markers_repairs_a_load_bearing_marker(raw, expected):
    assert api._strip_markers(raw, he=True) == expected


# The repair MUST be anchored to an actual deletion site. A blind "drop orphaned one-letter words"
# pass corrupts this corpus specifically: in Torah text a lone Hebrew letter is normally a chapter
# or section NUMBER. A first cut of this fix turned "פרק ב." into "פרק" and "א, ב, ג" into "א, ג" —
# silent citation corruption, far worse than the dangling preposition it set out to fix.
@pytest.mark.parametrize("raw", [
    "נלמד במסכת סוכה פרק ב.",
    "הסעיפים הם א, ב, ג.",
    "עיין בסימן ג, ובסעיף ה.",
])
def test_strip_markers_never_touches_a_lone_letter_with_no_marker(raw):
    assert api._strip_markers(raw, he=True) == raw


# A one-letter prefix only counts when it is not the tail of a Hebrew word — without that guard,
# "הכתוב[S1]" matches its own final ב and leaves "הכתו".
def test_strip_markers_does_not_eat_the_last_letter_of_the_preceding_word():
    assert api._strip_markers("הכתוב[S1] אומר כך.", he=True) == "הכתוב אומר כך."


@pytest.mark.parametrize("raw,expected", [
    ("וכך נאמר [S1].", "וכך נאמר."),                  # ordinary trailing marker, unchanged behaviour
    ("שני מקורות [S1, S5] כאן.", "שני מקורות כאן."),
    ("הערה (עיין שם) חשובה.", "הערה (עיין שם) חשובה."),  # mixed-Hebrew aside still survives
    ("סעיף (1) ברשימה.", "סעיף (1) ברשימה."),            # numeric aside still survives
])
def test_strip_markers_leaves_the_existing_behaviour_intact(raw, expected):
    assert api._strip_markers(raw, he=True) == expected


# ── Markdown headers/blockquotes reach the user as raw characters (2026-08-20) ─────────────────
# The interface renders plain text + **bold** + newlines only — no Markdown. SYSTEM_BASE_HE already
# tells the model this explicitly, and the model does not always follow it: a real answer used five
# separate "### heading" lines that showed up as literal hash marks, since nothing renders them.
def test_a_markdown_header_becomes_bold_not_raw_hashes():
    raw = '### מהי משמעות "מאי ואם נפשך לומר"?\n\nתשובה כלשהי כאן.'
    out = api._strip_markers(raw, he=True)
    assert "#" not in out
    assert out.startswith('**מהי משמעות "מאי ואם נפשך לומר"?**')


@pytest.mark.parametrize("hashes", ["#", "##", "###", "####"])
def test_headers_of_every_depth_are_converted(hashes):
    out = api._strip_markers(f"{hashes} כותרת\nגוף התשובה", he=True)
    assert out == "**כותרת**\nגוף התשובה"


def test_a_blockquote_marker_is_stripped_but_the_quote_text_survives():
    out = api._strip_markers("> וכי תימא בעריות קא מישתעי קרא", he=True)
    assert out == "וכי תימא בעריות קא מישתעי קרא"


def test_an_empty_header_produces_no_stray_bold_markers():
    out = api._strip_markers("###\nגוף התשובה", he=True)
    assert "#" not in out and "**" not in out


def test_a_bare_hash_mid_sentence_is_not_mistaken_for_a_header():
    """Only a '#' at the START of a line is a Markdown header — a hash appearing mid-sentence (e.g.
    a hashtag-like reference) must survive untouched."""
    raw = "המספר #1 ברשימה אינו כותרת."
    assert api._strip_markers(raw, he=True) == raw


def test_markdown_stripping_applies_to_english_answers_too():
    """The interface is markdown-free regardless of language — this must not be gated behind `he`."""
    out = api._strip_markers("### A Heading\nBody text", he=False)
    assert out == "**A Heading**\nBody text"


# ── Fix (2026-08-12): chavruta follow-up loses the tractate the conversation established.
# Bug: only user_turns[0] (the FIRST question) was carried into the anchor, so a tractate named
# in turn 2 was lost by turn 5. Now structural signals are harvested from the WHOLE conversation.
def test_conversation_signals_harvests_tractate_from_full_history():
    """The 5-turn conversation from the bug report should yield tractates == ['Sukkah']."""
    from chavruta.corpus.schema import Query

    user_turns = [
        "מה רשי אומר על בניית בית המקדש?",
        "ומה לגבי מה שהוא אומר במסכת סוכה בעניין הזה",
        "מה תוספות סובר על כך?",
        "האם תוספות חולק על רשי?",
        "האם יש מחלוקת בין רשי לתוספות על בניית המקדש",
    ]
    question = user_turns[-1]
    user_turns = user_turns[:-1]

    # Simulate the query after _resolve_query (which would have only turn1 + turn5 signals)
    rq = Query(text=user_turns[0] + " " + question, lang="he", intent=Intent.QA)
    # At this point, tractates would be empty (turn1 has no tractate, turn5 has no tractate)
    assert not rq.tractates

    # Apply the conversation signal harvesting
    api._conversation_signals(user_turns, question, rq)

    # Now tractates should include Sukkah from turn 2
    assert rq.tractates == ["Sukkah"]


def test_conversation_signals_explicit_current_tractate_wins_over_history():
    """An explicit tractate in the CURRENT question should win over one from earlier history."""
    from chavruta.corpus.schema import Query

    user_turns = [
        "מה אומר רשי על סוגיית השבת?",
        "ומה לגבי מה שהוא אומר במסכת סוכה בעניין הזה",
    ]
    question = "ומה אומר רשי במסכת ברכות על כך?"

    # Simulate _resolve_query already detecting the current question's tractate
    rq = Query(text=user_turns[0] + " " + question, lang="he", intent=Intent.QA)
    rq.tractates = ["Berakhot"]  # Explicit from current question

    # Apply conversation signal harvesting
    api._conversation_signals(user_turns, question, rq)

    # Current question's tractate should win, history should not override
    assert rq.tractates == ["Berakhot"]


# ── Fix (2026-08-02, caught live): a genuinely-grounded 'explain' answer still contained the bare
# sentence "אין תשובה במקורות — אמור זאת ואל תמציא" in the middle of real content — the model
# echoing a fragment of its own grounding instruction (pipeline.py::_agentic_generate's
# "## INSTRUCTIONS" block) as if it were an answer. Unlike bleed there's no meaning to preserve, so
# the whole sentence is dropped, and its OWN trailing separator too, so the sentence before it joins
# directly onto the sentence after it with no orphaned punctuation.
@pytest.mark.parametrize("raw,expected", [
    # the exact real leaked fragment (paraphrased, not byte-for-byte from the instruction text)
    ("פתיחה תקינה. אין תשובה במקורות — אמור זאת ואל תמציא. סיום תקין.",
     "פתיחה תקינה. סיום תקין."),
    ("אין תשובה במקורות — אמור זאת ואל תמציא. סיום תקין.", "סיום תקין."),          # leaked sentence first
    ("פתיחה תקינה. אין תשובה במקורות — אמור זאת ואל תמציא.", "פתיחה תקינה."),      # leaked sentence last
    ("תשובה נקייה לגמרי בלי שום דבר חשוד.", "תשובה נקייה לגמרי בלי שום דבר חשוד."),  # no-op
])
def test_strip_instruction_echo(raw, expected):
    assert api._strip_instruction_echo(raw, True) == expected


def test_strip_instruction_echo_noop_in_english():
    raw = "This is a fine English answer with no leaked instructions."
    assert api._strip_instruction_echo(raw, False) == raw


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

        def request(self, body_md, *, lang="he", token_budget=None):
            captured["job"] = body_md
            return ("תשובה מעוגנת [S1]" if result.hits else "רגע, תכוון אותי"), []

    # `profile` mirrors the real pipeline: _run_chavruta reads it to budget the request's tokens.
    return SimpleNamespace(retriever=_Retriever(), llm=_LLM(), _resolve_query=lambda q: q,
                           profile=SimpleNamespace(llm_max_tokens=512))


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
    # chapter-level: also the opening verse, since base texts are stored per-verse — in BOTH
    # spellings, because the commercial corpus stores 'Exodus.20.1' and the old one 'Exodus 20.1'
    assert with_ref_variants(["Exodus.20"]) == [
        "Exodus.20", "Exodus 20", "Exodus 20.1", "Exodus.20.1"]
    # a book whose name contains spaces: the commercial corpus underscores them. Emitting only the
    # spaced form is what made every base pasuk miss after the corpus swap (recall 50% -> 83%).
    assert with_ref_variants(["Mishnah Sukkah 3.5"]) == [
        "Mishnah Sukkah 3.5", "Mishnah_Sukkah.3.5"]
    # Talmud amud -> amud-linear opening segment, again in both spellings
    assert with_ref_variants(["Bava Metzia 2a"]) == [
        "Bava Metzia 2a", "Bava Metzia 3.1", "Bava_Metzia.3.1"]


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


# ── Tier1 (2026-07-27): "the opening of X" must resolve however Hebrew stacks the connectors ──
# The corpus_v1 eval showed the right commentator arriving on the WRONG verse — "מה מפרש רש\"י על
# תחילת בבא מציעא" returned Rashi on BM 148. The cause was upstream of retrieval: no named_ref was
# produced, so the anchoring path never ran. The connector lists were enumerated rather than composed,
# so "של ספר" (both words) and a tractate without the word "מסכת" fell through.
@pytest.mark.parametrize("text,expected", [
    ("מה כתוב בפסוק הראשון של ספר בראשית", "Genesis.1.1"),   # 'של' + 'ספר' together
    ("מה אומר רש\"י על הפסוק הראשון בבראשית", "Genesis.1.1"),  # the form that already worked
    ("הפסוק הראשון של התורה", "Genesis.1.1"),
    ("תחילת ספר ויקרא", "Leviticus.1.1"),
    ("מה מפרש רש\"י על תחילת בבא מציעא", "Bava Metzia.2a"),   # tractate WITHOUT 'מסכת'
    ("מה נידון בתחילת מסכת ברכות", "Berakhot.2a"),            # and with it
    ("הדף הראשון בבבא מציעא", "Bava Metzia.2a"),
])
def test_opening_reference_resolves_across_connector_forms(text, expected):
    from chavruta.intents.landmarks import resolve_landmarks
    assert expected in resolve_landmarks(text)


@pytest.mark.parametrize("text", [
    "בתחילת הדרך החלטנו ללמוד",        # 'תחילת' with no work named
    "מה קרה בתחילת השיעור",
    "הפסוק הראשון שקראנו אתמול",       # 'first verse' with no book
])
def test_opening_reference_needs_an_actual_work(text):
    """Loosening the connectors must not let 'תחילת' alone invent a ref — the work has to be named."""
    from chavruta.intents.landmarks import resolve_landmarks
    assert resolve_landmarks(text) == []


@pytest.mark.parametrize("text", ["פרק זה בשבת", "בפרק זה במסכת שבת", "פרק הוא בגיטין"])
def test_perek_demonstrative_not_gematria(text):
    """'פרק זה' = 'THIS chapter' — gematria('זה')=12 must NOT fabricate a perek number/daf."""
    from chavruta.intents.landmarks import resolve_landmarks
    assert not any(r.split()[0] in ("Shabbat", "Gittin") and r[-2:] != "2a" for r in resolve_landmarks(text))


# ── Tier1 (2026-07-26): naming a commentator from its ref, and the inverse ──────────────────────
# The commercial corpus carries neither `commentator_id` nor `anchor_ref`, so both directions have to
# be recovered from the ref string: reading one names the commentator, writing one reaches its
# comment on a given verse. Every expectation below is a ref verified to exist in the live corpus.
@pytest.mark.parametrize("ref,cid", [
    ("Rashi_on_Genesis.1.1.1", "rashi"),
    ("Or_HaChaim_on_Genesis.22.1.1", "or_hachaim"),
    ("Metzudat_David_on_Psalms.1.1.1", "metzudat_david"),
    ("Mizrachi_on_Rashi_on_Genesis.1.1.1", "mizrachi"),       # supercommentary: the FIRST author
    ("Targum_Onkelos_on_Genesis.1.1.1", "targum_onkelos"),    # '_on_' wins over the bare prefix
    ("Onkelos_Exodus.20.2", "onkelos"),                       # filed as a prefix, not a commentary
    ("Genesis.1.1", None),
    ("Netinah_LaGer,_Genesis.1.1.2", None),                   # a base text, not 'netinah_lager'
    ("", None),
])
def test_commentator_is_named_from_its_ref(ref, cid):
    from chavruta.corpus.refs import commentator_from_ref
    assert commentator_from_ref(ref) == cid


def test_commentary_refs_reach_the_named_commentator_on_a_verse():
    """The inverse: exact refs to fetch, since neither commentator_id nor anchor_ref can be filtered."""
    from chavruta.corpus.refs import commentary_refs

    out = commentary_refs(["Genesis.1.1", "Genesis 1.1"], ["rashi"], max_comments=3)
    assert out == ["Rashi_on_Genesis.1.1.1", "Rashi_on_Genesis.1.1.2", "Rashi_on_Genesis.1.1.3"]
    # The space form carries no commentaries — generating refs from it would be pure waste.
    assert not any(" " in r for r in out)
    # Capitalisation follows Sefaria, not naive title-case.
    assert commentary_refs(["Genesis.1.1"], ["or_hachaim"], max_comments=1) == \
        ["Or_HaChaim_on_Genesis.1.1.1"]
    # Onkelos has no '_on_' join and no comment index.
    assert commentary_refs(["Exodus.20.2"], ["onkelos"]) == ["Onkelos_Exodus.20.2"]
    assert commentary_refs(["Genesis.1.1"], []) == []


# ── Fix (2026-08-02): a real user reported source names in the citation panel are "usually in
# English" — true, the corpus stores every ref in Sefaria's English/transliterated spelling.
# hebrew_display_ref gives a best-effort Hebrew rendering for the common cases (Tanakh, Mishnah,
# Talmud Bavli base refs, and a curated set of classic commentators), verified against real refs
# pulled live from production, and returns None for anything it can't render confidently (never a
# half-translated guess).
@pytest.mark.parametrize("ref,expected", [
    ("Genesis.1.1", "בראשית 1:1"),
    ("Exodus.20.1", "שמות 20:1"),
    ("Mishnah_Sukkah.3.5", "משנה סוכה 3:5"),
    ("Rashi_on_Genesis.1.1.1", 'רש"י על בראשית 1:1'),
    ("Rashi_on_Genesis.1.1.2", 'רש"י על בראשית 1:1'),           # same verse, different comment index
    ("Bava_Metzia.3.1", "בבא מציעא 2."),                        # amud-linear N=3 -> daf 2 amud a
    ("Rashi_on_Bava_Metzia.3.1.1", 'רש"י על בבא מציעא 2.'),
    ("Bartenura_on_Mishnah_Bava_Metzia.1.1.1", "ברטנורא על משנה בבא מציעא 1:1"),
    ("Rambam_on_Mishnah_Bava_Metzia.1.1.1", 'רמב"ם על משנה בבא מציעא 1:1'),
    # Commentaries whose base can't be told apart from a bare tractate name once stripped (Tosefta,
    # Mishneh Torah, ...) used to DECLINE, because the curated tables were the only source of Hebrew
    # and letting `_split_book` see their base rendered chapter:halacha as a daf. They now render
    # through Sefaria's own title map, which carries the work's CATEGORY — so the Tosefta/Halakhah
    # base is recognised as not-Talmud and its numbers pass through untouched. What must never come
    # back is the daf conversion; `test_tosefta_base_never_gets_daf_math` below locks that.
    ("Maggid_Mishneh_on_Mishneh_Torah,_Plaintiff_and_Defendant.9.7.1",
     "מגיד משנה על משנה תורה, הלכות טוען ונטען 9:7:1"),
    ("Tosefta_Kifshutah_on_Bava_Metzia.1.1.1", "תוספתא כפשוטה על בבא מציעא 1:1:1"),
    ("Tosefta_Bava_Metzia_(Lieberman).1.1", "תוספתא בבא מציעא (ליברמן) 1:1"),
    (None, None),
    ("", None),
])
def test_hebrew_display_ref(ref, expected):
    from chavruta.corpus.refs import hebrew_display_ref
    assert hebrew_display_ref(ref) == expected


def test_tosefta_base_never_gets_daf_math():
    """A Tosefta commentary strips to a base spelled exactly like a Bavli tractate
    ('Tosefta_Kifshutah_on_Bava_Metzia' → 'Bava Metzia'). Rendering chapter 1 halacha 1 as 'daf 1a'
    is the specific wrong answer this module has always refused to give — caught live while wiring
    in the full Sefaria title map, when a derived commentator name let `_split_book` see that base.
    """
    from chavruta.corpus.refs import hebrew_display_ref
    out = hebrew_display_ref("Tosefta_Kifshutah_on_Bava_Metzia.1.1.1")
    assert out is not None
    assert "1." not in out.replace("1.1", "")   # no amud mark: it's chapter:halacha, not a daf
    assert out.endswith("1:1:1")


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

        def fetch_by_refs(self, name, refs, filters=None, *, limit=None):  # base verse stored SPACE-form only
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


# ── Tier1 (2026-07-26): a named commentator on a corpus whose `commentator_id` payload is EMPTY ──
# chavruta_commercial was indexed without the field on any of its 2.4M points, so the server-side
# filter matched nothing and "what does Rashi say on this verse" anchored to zero sources — the model
# was told there is no Rashi here while Rashi_on_Genesis.1.3.1 sat in the index. The name is
# recoverable from the ref, so it is derived on READ and the anchor is scoped by work instead.
def test_named_commentator_resolves_when_the_payload_field_is_empty():
    from chavruta.retrieval.hybrid import HybridRetriever

    class _Emb:
        def embed_query(self, text):
            return SimpleNamespace(dense=[0.1, 0.2], sparse={1: 0.5})

    class _Store:
        def __init__(self):
            self.anchor_filters = []
            self.asked = []

        def search(self, name, q, top_k, filters=None):
            return []                                   # a commentator-scoped search finds nothing

        def fetch_by_refs(self, name, refs, filters=None, *, limit=None):
            self.anchor_filters.append(filters)
            self.asked.append(list(refs))
            # As the corpus really stores it: `anchor_ref` is empty, so a lookup of the BASE ref
            # returns the verse alone. A commentary is reachable only under its own exact ref.
            out = []
            for r in refs:
                if r == "Rashi_on_Genesis.1.3.1":
                    out.append(Hit(chunk_id="r13", score=1.0,
                                   payload={"chunk_id": "r13", "ref": r,
                                            "text": "יהי אור — נעשה אור", "work_id": "tanakh"}))
                elif r == "Ibn_Ezra_on_Genesis.1.3.1":
                    out.append(Hit(chunk_id="i13", score=1.0,
                                   payload={"chunk_id": "i13", "ref": r,
                                            "text": "פירוש אחר", "work_id": "tanakh"}))
            return out

        def dense_scores(self, name, dense, filters=None, top_k=30):
            return {}

    store = _Store()
    prof = SimpleNamespace(hybrid=True, collection="c", relevance_threshold=0.5, rerank=False)
    q = Query(text="מה אומר רש\"י?", commentator_ids=["rashi"])
    q.named_refs = ["Genesis.1.3"]
    res = HybridRetriever(_Emb(), store, prof).retrieve(q, top_k=8)

    by_ref = {h.ref: h for h in res.hits}
    assert "Rashi_on_Genesis.1.3.1" in by_ref, "the named commentator never anchored"
    assert by_ref["Rashi_on_Genesis.1.3.1"].commentator_id == "rashi"     # derived, not stored
    assert not res.is_empty
    # It was reached by its OWN ref — asking for the base ref alone returns the verse and nothing else.
    assert "Rashi_on_Genesis.1.3.1" in store.asked[0]
    assert "Ibn_Ezra_on_Genesis.1.3.1" not in store.asked[0]   # only what was actually asked about
    # And never scoped by a field the corpus does not carry.
    assert all(not (f or {}).get("commentator_id") for f in store.anchor_filters)


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


# ── Global concurrency gate (2026-07-31): _run_query is the ONE choke point both the sync routes
# (inline) and the async job workers pass through, so bounding it here caps total concurrent
# generations system-wide — not per-route — which matters on a 2-vCPU free-tier box where letting
# an unbounded number of simultaneous synchronous /query requests run would bypass the job registry's
# own small worker pool entirely.
def test_run_query_returns_busy_response_when_at_capacity(monkeypatch):
    import threading
    monkeypatch.setattr(api, "_GENERATION_QUEUE_TIMEOUT_S", 0.05)
    monkeypatch.setattr(api, "_generation_semaphore", threading.Semaphore(1))
    api._generation_semaphore.acquire()   # simulate the one slot already being in use
    monkeypatch.setattr(api, "_run_query_impl", lambda *a, **k: (_ for _ in ())
                        .throw(AssertionError("must not run generation while at capacity")))
    resp = api._run_query("שאלה", "he", "qa", [])
    assert resp.grounded is False
    assert "עמוסה" in resp.answer


def test_run_query_returns_busy_response_in_english(monkeypatch):
    import threading
    monkeypatch.setattr(api, "_GENERATION_QUEUE_TIMEOUT_S", 0.05)
    monkeypatch.setattr(api, "_generation_semaphore", threading.Semaphore(1))
    api._generation_semaphore.acquire()
    resp = api._run_query("question", "en", "qa", [])
    assert resp.grounded is False
    assert "busy" in resp.answer.lower()


def test_run_query_releases_the_semaphore_after_success(monkeypatch):
    import threading
    monkeypatch.setattr(api, "_generation_semaphore", threading.Semaphore(1))
    monkeypatch.setattr(api, "_run_query_impl",
                        lambda *a, **k: api.QueryResponse(answer="ok", citations=[], grounded=True,
                                                          intent="qa", files=[]))
    api._run_query("q1", "he", "qa", [])
    # A single slot: this second call would hang until the timeout if the first call had leaked it.
    resp = api._run_query("q2", "he", "qa", [])
    assert resp.answer == "ok"


def test_run_query_releases_the_semaphore_after_a_degraded_exception(monkeypatch):
    import threading
    monkeypatch.setattr(api, "_generation_semaphore", threading.Semaphore(1))
    monkeypatch.setattr(api, "_run_query_impl",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    api._run_query("q1", "he", "qa", [])   # degrades to an error QueryResponse, must still release
    monkeypatch.setattr(api, "_run_query_impl",
                        lambda *a, **k: api.QueryResponse(answer="ok", citations=[], grounded=True,
                                                          intent="qa", files=[]))
    resp = api._run_query("q2", "he", "qa", [])
    assert resp.answer == "ok"


def test_run_query_records_how_many_generations_were_actually_concurrent(monkeypatch):
    """concurrent_at_start (app/db.py) must reflect what really happened, not the configured
    ceiling — start several _run_query calls at once (a semaphore roomy enough to admit them all)
    and confirm the peak observed count matches how many were genuinely in flight together."""
    import threading

    monkeypatch.setattr(api, "_generation_semaphore", threading.Semaphore(5))
    barrier = threading.Barrier(3)
    seen = []

    def _impl(*a, **k):
        barrier.wait(timeout=2)   # all three must be inside _run_query at the same instant
        seen.append(api._concurrency_at_start.get())
        return api.QueryResponse(answer="ok", citations=[], grounded=True, intent="qa", files=[])

    monkeypatch.setattr(api, "_run_query_impl", _impl)
    threads = [threading.Thread(target=api._run_query, args=(f"q{i}", "he", "qa", []))
               for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=3)

    assert len(seen) == 3
    assert max(seen) == 3            # all three really were in flight together
    assert api._in_flight_count == 0  # and the counter is back to zero once every thread finished


def test_record_event_writes_the_concurrency_context_var_into_the_usage_event(monkeypatch):
    """_record_event must read the SAME ContextVar _run_query sets, not a stale/default value —
    otherwise every usage_events row would silently record concurrency=0 regardless of reality."""
    captured = {}
    monkeypatch.setattr(api.db, "record_usage_event", lambda **kw: captured.update(kw))
    monkeypatch.setattr(api.db, "get_plan", lambda owner_id: "free")
    token = api._concurrency_at_start.set(4)
    try:
        api._record_event("local", "qa", None, {}, None, None, ms=10)
    finally:
        api._concurrency_at_start.reset(token)
    assert captured["concurrent_at_start"] == 4


def test_base_sources_for_refs_canonicalises_dedups_and_scores(monkeypatch):
    """base_sources_for_refs must look up the canonical ref, return RankedHits at score 1.0, and dedup."""
    calls = []

    class _Store:
        def fetch_by_refs(self, name, refs, filters=None, *, limit=None):
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
    from chavruta.corpus.schema import Intent, Query
    from chavruta.llm.base import SourceBlock
    src = SourceBlock(marker="", ref="Yoma 8.1", commentator_id=None, text="יום הכיפורים אסור באכילה")

    class _LLM:
        profile = "cloud"; model_id = "fake"
        source_fetcher = staticmethod(lambda qs: [src])

        def request(self, body_md, *, lang="he", token_budget=None):
            assert "===NEED_SOURCES===" in body_md            # the job invited a self-fetch
            return ("איסור אכילה ביום כיפור נלמד מעינוי [S1]", [src])

        def generate(self, *a, **k):
            raise AssertionError("generate must NOT be called when retrieval is empty — self-fetch first")

    ans = _selffetch_pipeline(_LLM()).ask(Query(text="מקור לאיסור אכילה ביום כיפור", lang="he", intent=Intent.QA))
    assert ans.grounded is True and ans.no_source is False
    assert any(c.ref == "Yoma 8.1" for c in ans.citations)    # cited the source it fetched itself


def test_qa_empty_retrieval_selffetch_fails_is_honest():
    from chavruta.corpus.schema import Intent, Query

    class _LLM:
        profile = "cloud"; model_id = "fake"
        source_fetcher = staticmethod(lambda qs: [])

        def request(self, body_md, *, lang="he", token_budget=None):
            # the loop's no-fetch degrade sentinel — nothing relevant could be pulled
            return ("לא הצלחתי להשיג מקורות מתאימים דרך הראג. נסה לנסח מחדש או לציין מקור מדויק.", [])

    ans = _selffetch_pipeline(_LLM()).ask(Query(text="שאלה על משהו שאינו בקורפוס", lang="he", intent=Intent.QA))
    assert ans.grounded is False and ans.citations == []      # honest no-source, never invented


# ── Fix (caught live 2026-08-05): a verbatim quote from a source the agentic ===NEED_SOURCES=== loop
# fetched — not part of the FIRST retrieval round — was flagged as "not found in the retrieved
# sources". pipeline.py's unverified_quotes(text, result.hits) checked only the ORIGINAL hits; the
# citation itself resolved fine (marker_map is separately extended with `fetched`), so an honestly-
# cited, faithfully-quoted answer got a spurious "unverified quote" caveat — dragging down the
# apparent grounding rate for something that was never actually a fabrication.
def test_agentically_fetched_source_quote_is_not_falsely_flagged():
    from chavruta.config.profile import Profile
    from chavruta.corpus.schema import Intent, Query
    from chavruta.llm.base import SourceBlock
    from chavruta.retrieval.base import RankedHit, RetrievalResult

    # First round's retrieval is non-empty but off-topic — thin enough that the model asks for more.
    first_round_hit = RankedHit(chunk_id="a", ref="Bava Metzia 1.1", text="טקסט לא קשור לשאלה", score=1.0)
    quote = "יאוש שלא מדעת אביי אמר לא הוי יאוש"
    fetched_src = SourceBlock(marker="", ref="Bava Metzia 21b", commentator_id=None, text=quote)

    class _Retriever:
        def retrieve(self, q, top_k):
            return RetrievalResult(hits=[first_round_hit], anchor_refs=[], is_empty=False)

    class _LLM:
        profile = "cloud"; model_id = "fake"
        source_fetcher = staticmethod(lambda qs: [fetched_src])

        def request(self, body_md, *, lang="he", token_budget=None):
            assert "===NEED_SOURCES===" in body_md            # thin first round invites a self-fetch
            return (f'התשובה נלמדת מכאן: "{quote}" [S2]', [fetched_src])

    prof = Profile(name="cloud", collection="c", top_k=5, relevance_threshold=0.0)
    pipeline = ChavrutaPipeline.from_backends(
        prof, embedding=None, store=None, llm=_LLM(),
        retriever=_Retriever(), router=SimpleNamespace(route=lambda q: q))

    ans = pipeline.ask(Query(text="מה המקור ליאוש שלא מדעת", lang="he", intent=Intent.QA))
    assert ans.grounded is True
    assert not any("לא נמצאו במקורות" in c for c in ans.caveats), (
        "a faithfully-quoted, agentically-fetched source must not be flagged as unverified")


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

        def fetch_by_refs(self, name, refs, filters=None, *, limit=None):
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

from chavruta.llm.agentic import parse_need_sources, run_agentic_loop  # noqa: E402
from chavruta.llm.base import SourceBlock  # noqa: E402


def test_parse_need_sources_variants():
    assert parse_need_sources("===NEED_SOURCES===\nסנהדרין כג\nזה בורר") == ["סנהדרין כג", "זה בורר"]
    assert parse_need_sources("a normal answer with [S1]") == []
    assert parse_need_sources("x\n=== NEED SOURCES ===\n- one\n- two\n===END===") == ["one", "two"]


def test_agentic_loop_bare_marker_with_no_queries_is_not_returned_as_answer():
    """Bug (2026-08-02, caught live on the Nebius deployment): Qwen3-235B replied with JUST the line
    '===NEED_SOURCES===' and no query lines after it, on a 'chavruta' discussion-style job. Since
    parse_need_sources() returns [] both for 'not a source request' AND for 'malformed source request
    with no queries', the OLD code (`if not queries: return answer`) treated the bare marker as a real
    written answer and showed the literal string '===NEED_SOURCES===' to the user. The fix checks
    is_source_request() first, so a marker with no queries spends a retry round instead of leaking."""
    replies = iter(["===NEED_SOURCES===", "עכשיו יש לי תשובה אמיתית [S1]"])
    seen_jobs = []

    def send(job_md):
        seen_jobs.append(job_md)
        return next(replies)

    def fetcher_should_not_be_called(qs):
        raise AssertionError("source_fetcher must not be called when there are no queries to fetch")

    text, fetched = run_agentic_loop(
        send, "## SOURCES\n### [S1] X\nbody", fetcher_should_not_be_called, "he")
    assert text == "עכשיו יש לי תשובה אמיתית [S1]"
    assert fetched == []
    assert len(seen_jobs) == 2   # the bare marker consumed a round instead of ending the loop


def test_agentic_loop_strips_bare_marker_if_final_round_still_relapses():
    """Defensive backstop: even on the FORCED final round (which explicitly instructs the model never
    to reply with the marker again), if a model still relapses into a bare '===NEED_SOURCES==='-only
    reply, the raw marker must never reach the user — it degrades to the honest no-fetch message
    instead of showing meaningless marker text."""
    from chavruta.llm.agentic import MAX_RETRIEVAL_ROUNDS, _NOFETCH_MSG

    def send(job_md):
        return "===NEED_SOURCES==="   # relapses every round, including the forced final one

    text, fetched = run_agentic_loop(send, "## SOURCES\n### [S1] X\nbody", lambda qs: [], "he")
    assert text == _NOFETCH_MSG["he"]
    assert "===NEED_SOURCES===" not in text


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
    from chavruta.llm.agentic import DEGRADE_MESSAGES, is_degrade_message
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

    monkeypatch.setattr(api.db, "get_messages", lambda sid, owner="local": [{"role": "user", "text": "q1"}])
    monkeypatch.setattr(api.db, "save_message", lambda *a, **k: 1)
    monkeypatch.setattr(api.db, "get_session_mode", lambda sid, owner="local": "chavruta")  # locked turn 1

    def _fake_run_query(question, lang, intent, history, **kw):
        captured["intent"] = intent
        return api.QueryResponse(answer="ok", citations=[], grounded=True, intent=intent, files=[])

    monkeypatch.setattr(api, "_run_query", _fake_run_query)
    # client tries to switch to 'lesson' mid-chat — must be ignored in favour of the locked 'chavruta'
    api.session_query("sid-1", QueryRequest(question="follow-up", lang="he", intent="lesson"), owner="local")
    assert captured["intent"] == "chavruta"


def test_session_query_legacy_session_falls_back_to_request_intent(monkeypatch):
    from app.api import QueryRequest
    captured = {}
    monkeypatch.setattr(api.db, "get_messages", lambda sid, owner="local": [{"role": "user", "text": "q1"}])
    monkeypatch.setattr(api.db, "save_message", lambda *a, **k: 1)
    monkeypatch.setattr(api.db, "get_session_mode", lambda sid, owner="local": None)  # legacy: no locked mode

    def _fake_run_query(question, lang, intent, history, **kw):
        captured["intent"] = intent
        return api.QueryResponse(answer="ok", citations=[], grounded=True, intent=intent, files=[])

    monkeypatch.setattr(api, "_run_query", _fake_run_query)
    api.session_query("sid-legacy", QueryRequest(question="q", lang="he", intent="qa"), owner="local")
    assert captured["intent"] == "qa"


# ── Bug (found live, 2026-08-02): every turn in a 'lesson'-mode conversation charged the scarce
# weekly lesson-count pool — including preliminary turns (resolving audience/grade/length, or a
# model ===CLARIFY===) that produce no lesson at all (see _run_lesson: these return files=[], no
# lesson_id). A teacher could burn their whole weekly allowance on back-and-forth before ever getting
# a real lesson. Fixed: _metered now settles a preliminary turn as an ordinary conversation-token
# spend, and charges ONE unit of the lesson pool ONLY for the turn that actually produced a real
# lesson (lesson_id set) — that turn's own token spend is suppressed instead (a lesson is paid for by
# its own pool, not tokens — see _charge_lesson_unit / _settle_tokens).
def test_metered_charges_lesson_pool_only_when_a_real_lesson_was_produced(monkeypatch):
    from chavruta.llm import metering as metering_mod

    lesson_charges = []
    settle_calls = []
    monkeypatch.setattr(api, "_charge_lesson_unit",
                        lambda owner, res, used_byok: (lesson_charges.append((owner, used_byok))
                                                       or False))
    monkeypatch.setattr(api, "_settle_tokens",
                        lambda owner, reserved, usage, intent, meter=api.db.TOKENS:
                            settle_calls.append(dict(usage)))
    monkeypatch.setattr(api, "_record_event", lambda *a, **k: None)

    # Preliminary turn: audience/grade/length still being resolved — no lesson yet. A real model call
    # may still have happened (e.g. a ===CLARIFY=== round), so simulate real token spend.
    def _prelim():
        metering_mod.record(500, 120)
        return api.QueryResponse(answer="למי מיועד השיעור?", citations=[], grounded=False,
                                 intent="lesson", files=[])

    api._metered("owner1", reserved=api.Reservation(20_000), intent="lesson", fn=_prelim)()
    assert lesson_charges == [], "a preliminary (no-lesson-yet) turn must not touch the lesson pool"
    assert settle_calls[-1] == {"prompt_tokens": 500, "completion_tokens": 120, "calls": 1}, \
        "a preliminary turn's real token spend must settle as an ordinary conversation-token charge"

    # The turn that actually builds the lesson: lesson_id is set. Also spends real (large) tokens —
    # which must NOT reach the conversation pool; the lesson pool pays for it instead.
    def _real_lesson():
        metering_mod.record(9000, 4000)
        return api.QueryResponse(answer="", citations=[], grounded=True, intent="lesson",
                                 files=[api.FileOut(name="x.doc", title="x", content="c")],
                                 lesson_id="abc123")

    api._metered("owner1", reserved=api.Reservation(20_000), intent="lesson", fn=_real_lesson)()
    assert lesson_charges == [("owner1", False)], "the real-lesson turn must charge exactly one lesson unit"
    assert settle_calls[-1] == {}, \
        "the real-lesson turn's token spend must be suppressed — paid for by the lesson pool instead"


# ── Tier0 (2026-07 audit): the agentic loop must enforce a CUMULATIVE output-token budget ──
# Bug: _INTENT_MAX_TOKENS defined careful per-intent budgets (LESSON: 30000) but the lesson path went
# through agentic_request, which HARDCODED max_tokens=8000 and never consulted the profile or the
# intent map. So the one number an operator would reach for to control spend had no effect on the
# most expensive path — and per-round caps multiply by the round count instead of bounding a request.

def test_agentic_loop_enforces_cumulative_token_budget():
    from chavruta.llm.agentic import agentic_request, is_degrade_message
    from chavruta.llm.base import LLMResult

    calls = []

    class _LLM:
        source_fetcher = staticmethod(lambda qs: [])          # never satisfies the ask → loop continues
        profile = "cloud"; model_id = "fake"

        def generate(self, prompt, *, lang, max_tokens, temperature):
            calls.append(max_tokens)
            # Always ask for more sources, so the loop would run every round if unbounded.
            return LLMResult(text="===NEED_SOURCES===\nמשהו", completion_tokens=400, prompt_tokens=100)

    answer, _ = agentic_request(_LLM(), "## JOB", lang="he", max_tokens=8000, token_budget=1000)

    # Rounds must be clamped to what remains of the budget, never the full per-round cap.
    assert calls[0] == 1000, f"first round should be clamped to the budget, got {calls[0]}"
    assert sum(c for c in calls) <= 8000, "per-round caps must not multiply past the budget"
    # 400 out/round vs a 1000 budget ⇒ round 3 has 200 left, round 4 would have 0 ⇒ loop stops.
    assert all(c > 0 for c in calls), "a zero-room round must not be sent"
    assert len(calls) <= 3, f"loop must stop once the budget is spent, made {len(calls)} calls"
    assert is_degrade_message(answer), "a budget stop with no answer must be an honest degrade"


def test_agentic_loop_uncapped_when_no_budget():
    """token_budget=None keeps the old behaviour — the bridge (which bills nothing) relies on it."""
    from chavruta.llm.agentic import agentic_request
    from chavruta.llm.base import LLMResult

    calls = []

    class _LLM:
        source_fetcher = None
        def generate(self, prompt, *, lang, max_tokens, temperature):
            calls.append(max_tokens)
            return LLMResult(text="תשובה [S1]", completion_tokens=999999)

    agentic_request(_LLM(), "## JOB", lang="he", max_tokens=8000, token_budget=None)
    assert calls == [8000], "with no budget the per-round cap is used as-is"


# ── Tier3 (public hosting): the LLM circuit breaker fails fast when the provider is down ──
# Bug (audit C4): with no breaker, every request during an outage waits out the full timeout and
# pins a worker thread, so one provider outage backs up the whole API. The breaker opens after N
# consecutive transient failures and fails fast for a cooldown.

def test_llm_circuit_breaker_opens_and_recovers():
    from chavruta.llm.cloud import LLMTransientError, _CircuitBreaker

    b = _CircuitBreaker(fails=3, cooldown_s=10.0)
    now = 100.0
    b.before(now)                                   # closed: allowed
    for _ in range(3):
        b.on_failure(now)                           # 3 consecutive transient failures → open
    import pytest as _pytest
    with _pytest.raises(LLMTransientError):
        b.before(now + 1)                           # open → fails fast, no network call
    with _pytest.raises(LLMTransientError):
        b.before(now + 9)                           # still within cooldown
    b.before(now + 11)                              # cooldown elapsed → half-open trial allowed
    b.on_success()
    b.before(now + 12)                              # success closed it again


def test_llm_circuit_breaker_success_resets_count():
    from chavruta.llm.cloud import _CircuitBreaker

    b = _CircuitBreaker(fails=2, cooldown_s=10.0)
    b.on_failure(0.0)
    b.on_success()          # a success in between must reset the consecutive counter
    b.on_failure(1.0)
    b.before(2.0)           # only 1 failure since the reset → still closed


# ── Feature (2026-07-18): async job queue — long lessons must not trip a proxy 504. The async
# endpoints return a job id immediately and run generation on a background pool; the client polls
# GET /jobs/{id}. These pin the wiring: the work actually runs, the result is the same shape as the
# sync endpoint, ownership is enforced synchronously, and polling is owner-scoped.

def _await_job(owner, jid, timeout=5.0):
    import time as _t
    deadline = _t.time() + timeout
    while _t.time() < deadline:
        job = api.jobs.get(jid, owner)
        assert job is not None
        if job.status in ("done", "error"):
            return job
        _t.sleep(0.01)
    raise AssertionError("async job did not finish in time")


def test_create_session_async_runs_in_background(monkeypatch):
    from app.api import QueryRequest
    monkeypatch.setattr(api.db, "create_session", lambda q, mode=None, owner_id="local": "sid-async")
    monkeypatch.setattr(api.db, "save_message", lambda *a, **k: 1)
    monkeypatch.setattr(api.db, "list_sessions",
                        lambda owner="local": [{"id": "sid-async", "first_q": "q", "created_at": "t"}])
    monkeypatch.setattr(api.db, "get_session",
                        lambda sid, owner="local": {"id": "sid-async", "first_q": "q", "created_at": "t"}
                        if sid == "sid-async" else None)
    monkeypatch.setattr(api, "_run_query",
                        lambda *a, **k: api.QueryResponse(answer="lesson body", citations=[],
                                                          grounded=True, intent="lesson", files=[]))

    accepted = api.create_session_async(QueryRequest(question="בנה שיעור", lang="he", intent="lesson"),
                                        owner="local")
    assert accepted.session_id == "sid-async"
    job = _await_job("local", accepted.job_id)
    assert job.status == "done"
    assert job.result["result"]["answer"] == "lesson body"
    assert job.result["id"] == "sid-async"


def test_session_query_async_rejects_unowned_synchronously(monkeypatch):
    from fastapi import HTTPException

    from app.api import QueryRequest
    # Not owned → get_messages returns empty → a 404 must be raised NOW (before any job is submitted),
    # so an unauthorized caller never enqueues work against someone else's chat.
    monkeypatch.setattr(api.db, "get_messages", lambda sid, owner="local": [])
    with pytest.raises(HTTPException) as e:
        api.session_query_async("sid-x", QueryRequest(question="q", lang="he"), owner="local")
    assert e.value.status_code == 404


def test_get_job_is_owner_scoped(monkeypatch):
    from fastapi import HTTPException

    from app.api import QueryRequest
    monkeypatch.setattr(api.db, "create_session", lambda q, mode=None, owner_id="local": "sid-o")
    monkeypatch.setattr(api.db, "save_message", lambda *a, **k: 1)
    monkeypatch.setattr(api.db, "list_sessions",
                        lambda owner="local": [{"id": "sid-o", "first_q": "q", "created_at": "t"}])
    monkeypatch.setattr(api.db, "get_session",
                        lambda sid, owner="local": {"id": "sid-o", "first_q": "q", "created_at": "t"}
                        if sid == "sid-o" else None)
    monkeypatch.setattr(api, "_run_query",
                        lambda *a, **k: api.QueryResponse(answer="a", citations=[], grounded=True,
                                                          intent="qa", files=[]))
    accepted = api.create_session_async(QueryRequest(question="q", lang="he"), owner="alice")
    _await_job("alice", accepted.job_id)
    # Bob polling Alice's job id must get a 404, not her lesson.
    with pytest.raises(HTTPException) as e:
        api.get_job(accepted.job_id, owner="bob")
    assert e.value.status_code == 404
    assert api.get_job(accepted.job_id, owner="alice").status == "done"


# ── Fix (2026-07-18 adversarial review): a first-query job that FAILS must not leave a blank,
# answer-less session stuck in the list. _first_query_work deletes the orphan on failure.
def test_create_session_async_deletes_orphan_on_failure(monkeypatch):
    from fastapi import HTTPException

    from app.api import QueryRequest
    deleted = {}
    monkeypatch.setattr(api.db, "create_session", lambda q, mode=None, owner_id="local": "sid-fail")
    monkeypatch.setattr(api.db, "save_message", lambda *a, **k: 1)
    monkeypatch.setattr(api.db, "delete_session",
                        lambda sid, owner="local": (deleted.__setitem__(sid, owner), True)[1])

    def boom(*a, **k):
        raise HTTPException(status_code=422, detail="unknown intent")

    monkeypatch.setattr(api, "_run_query", boom)
    accepted = api.create_session_async(QueryRequest(question="q", lang="he", intent="bad"), owner="local")
    job = _await_job("local", accepted.job_id)
    assert job.status == "error"
    assert deleted.get("sid-fail") == "local"      # orphan session cleaned up, not left behind


# ── Fix (2026-08-03, requested live): the daily/weekly quota bucket was keyed by the UTC date, not
# Israel local — "resets at midnight" meant UTC midnight, which lands 2-3h into the Israeli morning
# (winter/DST). A user near that window would see a NOT-YET-RESET quota well past their own local
# midnight. today_il() uses Asia/Jerusalem instead of UTC for the bucket key.
def test_today_il_uses_israel_local_date_not_utc():
    import app.db as db

    # 21:30 UTC on 2026-08-03 is already past midnight in Israel (00:30, +3h DST) — the daily bucket
    # must reflect the LOCAL date (08-04), not the still-previous UTC date (08-03).
    utc_after_israel_midnight = datetime(2026, 8, 3, 21, 30, tzinfo=UTC)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return utc_after_israel_midnight.astimezone(tz) if tz else utc_after_israel_midnight

    with unittest.mock.patch("app.db.datetime", _FixedDatetime):
        assert db.today_il() == "2026-08-04"


def test_week_days_still_starts_sunday_with_israel_local_dates():
    import app.db as db
    # 2026-08-02 is a Sunday; the week should run through the following Saturday, unaffected by
    # the switch from UTC to Israel-local dates (both use the same calendar-date string).
    assert db.week_days("2026-08-02") == [
        "2026-08-02", "2026-08-03", "2026-08-04", "2026-08-05",
        "2026-08-06", "2026-08-07", "2026-08-08",
    ]


from datetime import UTC, datetime  # noqa: E402
import unittest.mock  # noqa: E402


# _wants_full_lesson gates parsha/daf-yomi turns between the default chavruta-style back-and-forth
# and the full lesson (Word-doc) pipeline — "the model decides", via a cheap classification call
# (injected here via the llm= override so no real pipeline/classifier LLM is needed).
def test_wants_full_lesson_true_on_a_clear_yes():
    llm = _FakeLLM(reply="כן")
    assert api._wants_full_lesson("תבנה לי שיעור על הפרשה", llm=llm) is True


def test_wants_full_lesson_false_on_a_clear_no():
    llm = _FakeLLM(reply="לא")
    assert api._wants_full_lesson("מה רש\"י אומר כאן?", llm=llm) is False


def test_wants_full_lesson_defaults_false_on_llm_failure():
    llm = _FakeLLM(raises=True)
    assert api._wants_full_lesson("תבנה לי שיעור", llm=llm) is False


def test_wants_full_lesson_defaults_false_on_an_unclear_reply():
    llm = _FakeLLM(reply="אולי, קשה לדעת")
    assert api._wants_full_lesson("שאלה כלשהי", llm=llm) is False


# ── Fix (caught live 2026-08-11, from a real chat): two failures in one exchange ──────────────
# The user asked for the Rashi/Tosafot dispute about building the Beit HaMikdash and got
# "no Rashi commentary found here"; they replied "תנסה" and were served an essay on what the word
# נסה means in Tanakh. Two separate defects, both of them the system deciding on the model's behalf.

def test_named_commentators_missing_triggers_selffetch_before_declining():
    """A thematic explain/compare question can miss its named commentators simply because the first
    retrieval round scored other material higher. The model must get to search for them itself
    before the pipeline answers "not in the corpus" — the self-fetch loop used to be reachable only
    when retrieval came back COMPLETELY empty, so a non-empty-but-missing round declined outright."""
    from chavruta.config.profile import Profile
    from chavruta.corpus.schema import Intent, Query
    from chavruta.llm.base import SourceBlock
    from chavruta.retrieval.base import RankedHit, RetrievalResult

    # Retrieval returns real hits, but none of them are Rashi or Tosafot.
    other = RankedHit(chunk_id="x", ref="Middot.1.1", text="הר הבית", score=0.4, commentator_id=None)
    fetched = SourceBlock(marker="", ref="Rashi on Sukkah 41a", commentator_id="rashi",
                          text="בנין העתיד לבא")

    class _Retriever:
        def retrieve(self, q, top_k):
            return RetrievalResult(hits=[other], anchor_refs=[], is_empty=False)

    class _LLM:
        profile = "cloud"; model_id = "fake"
        source_fetcher = staticmethod(lambda qs: [fetched])

        def request(self, body_md, *, lang="he", token_budget=None):
            return ("רש\"י סובר שהמקדש העתידי יורד בנוי [S1]", [fetched])

    prof = Profile(name="cloud", collection="c", top_k=5, relevance_threshold=0.0)
    pipeline = ChavrutaPipeline.from_backends(prof, embedding=None, store=None, llm=_LLM(),
                                              retriever=_Retriever(),
                                              router=SimpleNamespace(route=lambda q: q))
    q = Query(text="מה המחלוקת בין רש\"י לתוספות", lang="he", intent=Intent.COMPARE,
              commentator_ids=["rashi", "tosafot"])
    ans = pipeline.ask(q)
    assert ans.grounded is True and ans.no_source is False
    assert any(c.ref == "Rashi on Sukkah 41a" for c in ans.citations)


def test_short_followup_retrieves_on_the_previous_topic():
    """'תנסה' has no topic of its own: retrieval used to embed the bare word and match the corpus's
    sources about the CONCEPT of a test, so the model explained what ניסיון means instead of
    retrying. The follow-up's search_text must carry the previous question; the text the MODEL sees
    must stay exactly what the user typed."""
    from chavruta.config.profile import Profile
    from chavruta.corpus.schema import Intent, Query, Turn

    prof = Profile(name="cloud", collection="c", top_k=5, relevance_threshold=0.0)
    pipeline = ChavrutaPipeline.from_backends(prof, embedding=None, store=None, llm=None,
                                              retriever=SimpleNamespace(),
                                              router=SimpleNamespace(route=lambda q: q))
    prev = "מה המחלוקת בין רש\"י לתוספות לגבי בניית בית המקדש"
    q = Query(text="תנסה", lang="he", intent=Intent.QA, search_text="תנסה")
    out = pipeline._anchor_followup(q, [Turn(role="user", text=prev),
                                        Turn(role="assistant", text="לא נמצא בקורפוס")])
    assert prev in out.search_text          # retrieval now sees the actual topic
    assert out.text == "תנסה"               # the model still reads what the user wrote


def test_long_followup_is_not_anchored():
    """A full question mid-conversation stands on its own — anchoring it would drag the previous
    topic into a deliberate change of subject."""
    from chavruta.config.profile import Profile
    from chavruta.corpus.schema import Intent, Query, Turn

    prof = Profile(name="cloud", collection="c", top_k=5, relevance_threshold=0.0)
    pipeline = ChavrutaPipeline.from_backends(prof, embedding=None, store=None, llm=None,
                                              retriever=SimpleNamespace(),
                                              router=SimpleNamespace(route=lambda q: q))
    new_q = "עכשיו שאלה אחרת לגמרי על הלכות מוקצה בשבת ומה אומר השולחן ערוך"
    q = Query(text=new_q, lang="he", intent=Intent.QA, search_text=new_q)
    out = pipeline._anchor_followup(q, [Turn(role="user", text="שאלה קודמת על בית המקדש")])
    assert out.search_text == new_q


def test_followup_without_history_is_unchanged():
    from chavruta.config.profile import Profile
    from chavruta.corpus.schema import Intent, Query

    prof = Profile(name="cloud", collection="c", top_k=5, relevance_threshold=0.0)
    pipeline = ChavrutaPipeline.from_backends(prof, embedding=None, store=None, llm=None,
                                              retriever=SimpleNamespace(),
                                              router=SimpleNamespace(route=lambda q: q))
    q = Query(text="תנסה", lang="he", intent=Intent.QA, search_text="תנסה")
    assert pipeline._anchor_followup(q, None).search_text == "תנסה"


def test_base_source_floor_filters_commentary_by_ref_not_unit_type():
    """The floor exists to reserve slots for the BASE text (pasuk/mishnah/daf) against its own
    commentaries. It filtered on unit_type="source" believing commentary couldn't satisfy that — but
    every point in this corpus carries unit_type="source", and Rashi_on_Bava_Metzia.42.1.1 and
    Bava_Metzia.42.1 are identical on both work_id and unit_type. The ref shape is the only signal.
    """
    from chavruta.corpus.refs import is_commentary_ref

    assert is_commentary_ref("Rashi_on_Bava_Metzia.42.1.1")
    assert is_commentary_ref("Tosafot_on_Sukkah.81.11.1")
    assert not is_commentary_ref("Bava_Metzia.42.1")
    assert not is_commentary_ref("Genesis.1.1")

    import inspect

    from chavruta.retrieval import hybrid
    src = inspect.getsource(hybrid.HybridRetriever._retrieve_impl)
    assert 'unit_type": "source"' not in src, (
        "the base-source floor must not filter on unit_type — it is 'source' for every point"
    )
    assert "is_commentary_ref" in src


# ── Fix (2026-08-12): a chavruta conversation lost the sugya it had been studying. The tractate fix
# above recovers the MASECHET from the wording of earlier turns, but not the daf — and a follow-up
# like "האם הם חולקים?" names nothing at all, so there is nothing to parse. The surest record of
# which sugya is live is what the earlier ANSWERS already cited: those refs are known-relevant,
# because the answers were grounded in them. api._prepare_continue was decoding citations out of the
# DB and then dropping them on the floor when it built Turn(role, text).
def test_turn_carries_the_refs_it_cited():
    from chavruta.corpus.schema import Turn

    assert Turn(role="user", text="שאלה").refs == []          # default stays empty
    assert Turn(role="assistant", text="ת", refs=["Sukkah.81"]).refs == ["Sukkah.81"]


def test_carried_refs_are_most_recent_first_and_deduplicated():
    from chavruta.corpus.schema import Turn

    history = [
        Turn(role="user", text="q1"),
        Turn(role="assistant", text="a1", refs=["Genesis.1.1", "Rashi_on_Genesis.1.1.1"]),
        Turn(role="user", text="q2"),
        Turn(role="assistant", text="a2", refs=["Sukkah.81", "Genesis.1.1"]),  # repeat must not double
    ]
    assert api._carried_refs(history) == ["Sukkah.81", "Genesis.1.1", "Rashi_on_Genesis.1.1.1"]


def test_carried_refs_ignores_user_turns_and_missing_refs():
    from chavruta.corpus.schema import Turn

    assert api._carried_refs([Turn(role="user", text="בסוכה מא")]) == []
    assert api._carried_refs([]) == []
    assert api._carried_refs(None) == []


def test_carried_refs_is_bounded():
    from chavruta.corpus.schema import Turn

    many = [f"Sukkah.{i}" for i in range(api._MAX_CARRIED_REFS + 5)]
    history = [Turn(role="assistant", text="a", refs=many)]
    assert len(api._carried_refs(history)) == api._MAX_CARRIED_REFS


def test_conversation_signals_prefers_cited_refs_over_refs_parsed_from_prose():
    """A ref the conversation actually grounded an answer in beats one inferred from wording."""
    from chavruta.corpus.schema import Intent, Query, Turn

    rq = Query(text="האם הם חולקים?", lang="he", intent=Intent.QA)
    history = [Turn(role="assistant", text="a", refs=["Rashi_on_Sukkah.81.11.2"])]
    api._conversation_signals(["ומה בבראשית א:א?"], "האם הם חולקים?", rq, history)
    assert rq.named_refs == ["Rashi_on_Sukkah.81.11.2"]


def test_conversation_signals_falls_back_to_parsed_refs_with_no_cited_ones():
    from chavruta.corpus.schema import Intent, Query

    rq = Query(text="x", lang="he", intent=Intent.QA)
    api._conversation_signals(["ומה בבראשית א:א?"], "האם הם חולקים?", rq, history=[])
    assert rq.named_refs == ["Genesis.1.1"]


# ── The per-intent generation budgets and the quota RESERVATIONS that pay for them have to move
# together: a completion is weighted x3, so a budget bigger than a third of its own reservation
# means a single answer can overspend what was reserved for the whole turn (2026-08-12).
def test_every_intent_reservation_covers_its_own_generation_budget():
    import app.plans as plans
    from chavruta.config.profile import Profile
    from chavruta.corpus.schema import Intent
    from chavruta.pipeline.pipeline import _max_tokens_for

    profile = Profile()
    for intent, name in ((Intent.QA, "qa"), (Intent.EXPLAIN, "explain"),
                         (Intent.COMPARE, "compare"), (Intent.HALACHA, "halacha")):
        budget = _max_tokens_for(intent, profile)
        reserved = plans.token_estimate(name)
        assert reserved >= budget * plans.COMPLETION_WEIGHT, (
            f"{name}: reserving {reserved} cannot cover a {budget}-token answer "
            f"(x{plans.COMPLETION_WEIGHT} = {budget * plans.COMPLETION_WEIGHT})"
        )


def test_every_paid_tier_is_exactly_its_stated_multiple_of_free():
    """The UI states a RATIO ('3x the usage') and never a number, so the ratio must be literally
    true in every dimension. Raising the free tier without recomputing the paid ones breaks it."""
    import app.plans as plans

    free = plans.TIERS[0]
    assert free.id == "free" and free.multiple == 1
    for t in plans.TIERS[1:]:
        assert t.daily_tokens == free.daily_tokens * t.multiple, t.id
        assert t.weekly_tokens == free.weekly_tokens * t.multiple, t.id
        assert t.weekly_lessons == free.weekly_lessons * t.multiple, t.id


# ── Provider prompt-caching visibility (2026-08-12). Nebius does not document prompt caching, and
# the question "does it cache, and does OUR prompt shape actually hit" cannot be settled from docs —
# so read the figure the OpenAI-compatible response already carries. A provider that does not
# implement it omits the field, and a steady 0 in the logs is itself the answer.
def test_cached_prompt_tokens_reads_the_openai_field():
    from types import SimpleNamespace
    from chavruta.llm.cloud import _cached_prompt_tokens

    usage = SimpleNamespace(prompt_tokens_details=SimpleNamespace(cached_tokens=1024))
    assert _cached_prompt_tokens(usage) == 1024
    assert _cached_prompt_tokens(SimpleNamespace(prompt_tokens_details={"cached_tokens": 7})) == 7


@pytest.mark.parametrize("usage", [
    None,                                                     # no usage at all
    SimpleNamespace(prompt_tokens=10),                        # provider omits the details block
    SimpleNamespace(prompt_tokens_details=None),
    SimpleNamespace(prompt_tokens_details=SimpleNamespace(cached_tokens=None)),
    SimpleNamespace(prompt_tokens_details=SimpleNamespace(cached_tokens="nonsense")),
])
def test_cached_prompt_tokens_is_zero_when_unreported(usage):
    """Reading this must never be able to break a real call — it is diagnostics riding along."""
    from chavruta.llm.cloud import _cached_prompt_tokens

    assert _cached_prompt_tokens(usage) == 0


# ── The session-creation envelope hid every lesson and every citation ─────────
# _first_query_work returns {"id", "first_q", "created_at", "result": <the answer>}, and both
# _lesson_id_of and _record_event read the OUTER dict. Every key they wanted was simply absent, so
# lesson_id came back "" and the lesson pool was never charged — and since the UI starts a new chat
# per lesson, that was most lessons in the product. grounded/citations came back None too, which is
# the figure the admin dashboard reports as the product's grounding rate.
def _lesson_answer():
    return api.QueryResponse(answer="שיעור", citations=[{"ref": "Genesis.1.1", "text": "t"}],
                             grounded=True, intent="lesson",
                             files=[{"name": "a.docx", "title": "t", "content": "c"}],
                             lesson_id="L1")


def test_a_lesson_built_on_the_first_turn_of_a_new_chat_is_still_a_lesson():
    envelope = {"id": "s1", "first_q": "q", "created_at": "now", "result": _lesson_answer()}
    assert api._lesson_id_of(envelope) == "L1"
    assert api._lesson_id_of(_lesson_answer()) == "L1"          # the follow-up shape still works


def test_the_envelope_does_not_report_a_grounded_answer_as_ungrounded():
    envelope = {"id": "s1", "first_q": "q", "created_at": "now", "result": _lesson_answer()}
    got = api._answer_payload(envelope)
    assert got["grounded"] is True and len(got["citations"]) == 1


def test_a_new_chat_that_produces_a_lesson_charges_the_lesson_pool(monkeypatch, tmp_path):
    """The end-to-end invariant the two unit tests above only approach from either side."""
    monkeypatch.setattr(api.db, "DB_PATH", tmp_path / "lessons.db")
    monkeypatch.setattr(api.db, "_conn", None)
    api.db.get_conn()
    monkeypatch.setattr(api, "_record_event", lambda *a, **k: None)
    monkeypatch.setenv("CHAVRUTA_LESSONS_WEEK_FREE", "5")

    api._metered("teacher1", api.Reservation(20_000), "lesson",
                 lambda: {"id": "s1", "first_q": "q", "created_at": "now",
                          "result": _lesson_answer()})()
    assert api.db.usage_this_week("teacher1", meter=api.db.LESSON) == 1


# ── A sources section that named no sources (reported 2026-08-14) ────────────
# A user asked where the quotes in an answer came from and got a numbered list whose every entry
# read "– מופיע ב-  וב-:" — nineteen times. The model had written "מופיע ב-[S1] וב-[S3]:", and marker
# stripping took the markers and left the prepositions.
#
# _CARRIER_MARKER_RE existed for exactly this and missed on two counts: it allowed no maqaf/hyphen
# between the prefix and the marker ("ב-[S1]" is the ordinary way to attach a Hebrew prefix to a
# bracketed token), and it allowed only ONE prefix letter, so the very common vav+preposition
# ("וב-[S3]") could not match at all.
@pytest.mark.parametrize("raw,expected", [
    ("– מופיע ב-[S1] וב-[S3]:", "– מופיע:"),
    ("מופיע ב-[S1]:", "מופיע:"),
    ("נאמר ול-[S2] יש דעה אחרת", "נאמר יש דעה אחרת"),
    ("כתוב ב[S2] שהוא", "כתוב שהוא"),          # the un-hyphenated form still works
])
def test_a_hebrew_prefix_does_not_survive_the_marker_it_was_attached_to(raw, expected):
    assert api._strip_markers(raw, he=True) == expected


@pytest.mark.parametrize("raw", [
    "פרק ב. הסעיפים א, ב, ג",     # lone Hebrew letters here are NUMBERS, not prefixes
    "ובסעיף ה נאמר",
])
def test_lone_hebrew_letters_that_are_not_carrying_a_marker_are_untouched(raw):
    """The reason this repair is keyed on adjacency to a marker. In a Torah corpus a lone letter is
    usually a chapter or section number, and a blind 'drop orphaned one-letter words' pass would
    silently corrupt citations across the product."""
    assert api._strip_markers(raw, he=True) == raw


def test_a_marker_glued_to_a_word_does_not_eat_the_word():
    """"הכתוב[S1]" must not lose its final ב — the lookbehind is what stops the word's own last
    letter reading as a carrier prefix."""
    assert api._strip_markers("הכתוב[S1] אומר", he=True) == "הכתוב אומר"


# ── The model's own source list, behind the HHH sentinel ─────────────────────
# Added 2026-08-14 after a user asked where an answer's quotes came from and got nothing usable.
# The block is cut out of the displayed answer and carried beside it, exactly as [S#] markers are.
def test_the_source_list_is_cut_out_of_the_answer():
    body, note = api._split_source_note(
        'תשובה כאן.\n\nHHH\n1. רש"י על בראשית — צרפת, המאה ה-11.')
    assert body == "תשובה כאן."
    assert note.startswith("1. רש")


@pytest.mark.parametrize("delim", ["HHH", "===HHH===", "  **HHH**  ", "‏HHH"])
def test_the_sentinel_survives_the_decoration_a_model_adds_unprompted(delim):
    """Bolded, indented, wrapped in equals signs, prefixed with an RTL mark — the same decorations
    _LESSON_SPLIT_RE already tolerates, because the model applies them without being asked."""
    body, note = api._split_source_note(f"תשובה.\n{delim}\nרשימה")
    assert body == "תשובה." and note == "רשימה"


def test_an_answer_without_the_sentinel_is_returned_untouched():
    assert api._split_source_note("סתם תשובה בלי רשימה") == ("סתם תשובה בלי רשימה", "")
    assert api._split_source_note("") == ("", "")


def test_the_source_list_is_hidden_from_the_foreign_language_pass():
    """The whole reason the split happens before cleaning. A work's name is often the only Latin
    text in a Hebrew answer, so left in place the list trips _has_bleed and _fix_bleeding_sentences
    spends a model call per line rewriting away the very names the list exists to carry."""
    whole = 'תשובה נקייה לגמרי.\n\nHHH\nBirkat_Asher_on_Torah — לא ידוע.'
    body, note = api._split_source_note(whole)
    assert api._has_bleed(whole) is True      # would have been "fixed"
    assert api._has_bleed(body) is False      # …but the answer itself is clean
    assert "Birkat_Asher" in note             # and the name survives intact


def test_the_instruction_is_off_unless_the_request_turns_it_on():
    """It reshapes every Hebrew answer, so it ships to the operator alone first."""
    import chavruta.llm.base as lb

    prompt = lb.GroundedPrompt(system="s", question="q", sources=[
        lb.SourceBlock(marker="S1", ref="Rashi_on_Genesis.1.1.1", commentator_id="rashi", text="t")])

    assert "HHH" not in lb.render_messages(prompt, "he")[-1]["content"]
    token = lb.set_source_note(True)
    try:
        assert "HHH" in lb.render_messages(prompt, "he")[-1]["content"]
        # English answers are unchanged — the Latin-ref problem this solves is Hebrew-only.
        assert "HHH" not in lb.render_messages(prompt, "en")[-1]["content"]
    finally:
        lb.reset_source_note(token)
    assert "HHH" not in lb.render_messages(prompt, "he")[-1]["content"]


def test_render_messages_now_forbids_copying_the_raw_ref_into_prose():
    """Caught live 2026-08-20: a real answer wrote 'ביומא 148:10' — the corpus's own internal
    segment number for the source header it was shown ('יומא — Yoma.148.10') — straight into the
    prose instead of the human daf:amud form. Both language variants must carry the prohibition."""
    import chavruta.llm.base as lb

    prompt = lb.GroundedPrompt(system="s", question="q", sources=[
        lb.SourceBlock(marker="S1", ref="Yoma.148.10", commentator_id=None, text="t")])

    he_content = lb.render_messages(prompt, "he")[-1]["content"]
    assert "זיהוי פנימי" in he_content or "מזהה פנימי" in he_content

    en_content = lb.render_messages(prompt, "en")[-1]["content"]
    assert "internal reference" in en_content


def test_chavruta_job_prompt_also_forbids_copying_the_raw_ref():
    """Chavruta mode builds its OWN source header (no Hebrew-name prefix at all — app/api.py's
    _chavruta_job_md shows '### [S#] <ref>' directly), so it needs the same instruction, not just
    render_messages (which chavruta mode does not go through)."""
    job = api._chavruta_job_md("שאלה", [], "he", [])
    assert "Yoma.148.10" in job or "internal identifier" in job.lower() or "פנימי" in job


# ── The base-text floor reserved nothing (reported 2026-08-14) ────────────────
# A user asked for the source of a well-known idea and got a stack of works nobody has heard of,
# with not one base text in the top 8. The floor meant to prevent exactly that appended its
# candidates and boosted none of them, so they went back into the same score sort and lost — a
# pasuk at 0.30 does not survive next to a commentary at 0.66.
def test_the_base_text_floor_actually_lifts_what_it_reserves():
    from chavruta.retrieval import hybrid

    assert hybrid._BASE_BOOST > 0, "the floor reserves a slot it cannot hold"
    # Level with the other two floors: a base text is worth as much as a foundational-work hit.
    assert hybrid._BASE_BOOST == hybrid._FOUNDATIONAL_BOOST


def test_a_base_text_now_survives_next_to_a_commentary_that_scored_higher():
    """The reported failure in miniature, at the scores the live corpus actually produced."""
    from chavruta.retrieval import hybrid

    commentary, base = 0.5625, 0.55           # observed on the real query, 2026-08-14
    assert base < commentary                   # before: the pasuk loses and is cut
    assert min(base + hybrid._BASE_BOOST, 0.98) > commentary


def test_the_lifted_base_text_still_cannot_outrank_a_named_ref():
    """A base text the user did not ask for by name must not masquerade as one they did — the
    named-ref anchor sits at 0.99 and this is capped below it."""
    from chavruta.retrieval import hybrid

    assert min(0.99 + hybrid._BASE_BOOST, 0.98) < 0.99


def test_the_base_boost_is_measurable_rather_than_permanent():
    """Every constant in hybrid.py is a judgement; the ones that matter are knobs the nightly run
    can overrule. 0.0 must be a candidate so the sweep can say the lift does not help."""
    import importlib.util
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2] / "scripts" / "tune_retrieval.py").read_text(
        encoding="utf-8")
    knobs = src[src.index("KNOBS: dict[str, list] = {"):src.index("HUMAN_SETS")]
    assert "_BASE_BOOST" in knobs
    spec = importlib.util.spec_from_loader("k", loader=None)
    mod = importlib.util.module_from_spec(spec)
    exec(compile(knobs, "k", "exec"), mod.__dict__)          # noqa: S102
    assert 0.0 in mod.KNOBS["_BASE_BOOST"]


# ── The source list had nowhere to live (same day) ───────────────────────────
def test_the_source_list_survives_a_reload(tmp_path, monkeypatch):
    """It was returned in the API response and stored nowhere, so it vanished the moment the
    conversation was reopened — the feature would have read as broken rather than absent."""
    import app.db as db

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "note.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    sid = db.create_session("שאלה", owner_id="o-1")
    db.save_message(sid, "assistant", "תשובה", intent="qa",
                    source_note="1. רש\"י על בראשית — צרפת, המאה ה-11.")

    reloaded = db.get_messages(sid, "o-1")
    assert reloaded[-1]["source_note"].startswith("1. רש")


def test_a_message_saved_without_a_source_list_reads_back_empty(tmp_path, monkeypatch):
    """Most messages have none — it must be an empty string, never NULL, so the API model and the
    client can treat it as a plain string everywhere."""
    import app.db as db

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "note2.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    sid = db.create_session("שאלה", owner_id="o-1")
    db.save_message(sid, "assistant", "תשובה", intent="qa")

    assert db.get_messages(sid, "o-1")[-1]["source_note"] == ""


def test_the_source_list_does_not_show_the_reader_raw_markers():
    """Seen on the first live run: the model opens each line "[S1] נשמת חיים…". A marker means
    nothing to a reader — that is why they are stripped from the answer — and the note is
    reader-facing. Only the marker pass runs here; the foreign-language scrub must still never
    touch this block, because a work's name is often the only Latin text in it."""
    body, note = api._split_source_note(
        'תשובה.\nHHH\n[S1] נשמת חיים — חיבור קבלי.\n[S8] Toldot_Yaakov_Yosef — ספר חסידי.')
    assert body == "תשובה."
    assert "[S1]" not in note and "[S8]" not in note
    assert note.startswith("נשמת חיים")
    assert "Toldot_Yaakov_Yosef" in note, "the scrub must not have run on the note"


def test_the_source_list_gate_covers_every_generation_route():
    """It was set on /query alone, and the app posts to /sessions/{id}/query — so the trailing
    source list worked in a direct call and never once through the UI. Six answers went out with an
    empty note before anyone noticed, because the check that "verified" it bypassed the route.

    _run_query is the one funnel every generation path goes through, so the gate belongs there.
    """
    import inspect

    src = inspect.getsource(api._run_query)
    assert "set_source_note(_source_note_enabled(owner_id))" in src
    assert "reset_source_note" in src, "the flag would leak into the next request on this worker"
    # …and no route sets it on its own any more, which would double-set and leave a stale token.
    assert inspect.getsource(api.query).count("set_source_note") == 0


# ── Sources the model used without marking (the original 2026-08-14 request) ─
# The panel is built from [S#] markers, so a source the model leaned on without writing a marker
# never reaches the reader. Measured on a real answer: 16 citations against 19 lines in the model's
# own list. Closing that gap is what the source list was asked for.
def test_refs_are_picked_out_of_the_source_list_lines():
    """The model copies from a block formatted "<hebrew name> — <ref>" and often takes half of it,
    so the ref is found inside the line rather than the line parsed as a whole."""
    refs = api._refs_in_source_note(
        "מדרש אגדה, Numbers.22.5.1\nReggio on Torah, Numbers.22.9.1\nהדר זקנים, Exodus.1.10.2")
    assert refs == ["Numbers.22.5.1", "Reggio_on_Torah,_Numbers.22.9.1", "Exodus.1.10.2"]


def test_a_source_the_model_used_without_marking_reaches_the_panel(monkeypatch):
    """The whole point: [S#] gives 16, the list names 19, and the reader should see all of them."""
    from types import SimpleNamespace

    monkeypatch.setattr(api, "_fetch_refs", lambda refs: [
        SimpleNamespace(payload={"ref": "Numbers.22.5.1", "text_he": "טקסט"})])
    monkeypatch.setattr(api.db, "record_guard_finding", lambda *a, **k: None)
    out = api.QueryResponse(answer="a", citations=[], grounded=True, intent="qa")

    api._widen_citations_from_note(out, "מדרש אגדה, Numbers.22.5.1")

    assert [c.ref for c in out.citations] == ["Numbers.22.5.1"]
    assert out.citations[0].text_he == "טקסט"


def test_a_line_that_resolves_to_nothing_never_becomes_a_citation(monkeypatch):
    """The list is an INDEX into real material, never a source of truth — the first live runs
    invented an author for the Ben Ish Chai and a parasha called "איקה". A fabricated line must not
    be able to turn itself into a citation."""
    from types import SimpleNamespace

    monkeypatch.setattr(api, "_fetch_refs", lambda refs: [
        SimpleNamespace(payload={"ref": "Numbers.22.5.1", "text_he": "טקסט"})])
    logged: list = []
    monkeypatch.setattr(api.db, "record_guard_finding",
                        lambda kind, intent, detail, **k: logged.append((kind, detail)))
    out = api.QueryResponse(answer="a", citations=[], grounded=True, intent="qa")

    api._widen_citations_from_note(out, "מדרש אגדה, Numbers.22.5.1\nבדוי, Invented.99.99.99")

    assert [c.ref for c in out.citations] == ["Numbers.22.5.1"]
    # …and the one that resolved to nothing is recorded FOR THE OPERATOR, with no user-facing effect.
    assert logged and logged[0][0] == "source_note_unresolved"
    assert "Invented.99.99.99" in logged[0][1]["refs"]


def test_a_source_already_cited_is_not_added_twice(monkeypatch):
    called: list = []
    monkeypatch.setattr(api, "_fetch_refs", lambda refs: called.append(refs) or [])
    out = api.QueryResponse(answer="a", grounded=True, intent="qa", citations=[
        api.CitationOut(ref="Numbers.22.5.1")])

    api._widen_citations_from_note(out, "מדרש אגדה, Numbers.22.5.1")

    assert len(out.citations) == 1
    assert called == [], "already-cited refs must not even be looked up"


def test_a_broken_lookup_never_costs_the_user_their_answer(monkeypatch):
    """This runs on the answer path. A diagnostic that can break an answer is worse than none."""
    def boom(refs):
        raise RuntimeError("qdrant down")

    monkeypatch.setattr(api, "_fetch_refs", boom)
    out = api.QueryResponse(answer="a", citations=[], grounded=True, intent="qa")
    api._widen_citations_from_note(out, "מדרש אגדה, Numbers.22.5.1")   # must not raise
    assert out.answer == "a"


def test_a_real_ref_never_shown_this_turn_is_not_widened(monkeypatch):
    """Passing (1) corpus-exists isn't enough — a real work the model was never given for THIS
    question is not evidence it actually used it. Measured live 2026-08-14: of 30 unique refs one
    real answer named, 20 resolved in the corpus but were never in that turn's retrieved set."""
    from types import SimpleNamespace

    monkeypatch.setattr(api, "_fetch_refs", lambda refs: [
        SimpleNamespace(payload={"ref": "Numbers.22.5.1", "text_he": "טקסט"})])
    logged: list = []
    monkeypatch.setattr(api.db, "record_guard_finding",
                        lambda kind, intent, detail, **k: logged.append((kind, detail)))
    out = api.QueryResponse(answer="a", citations=[], grounded=True, intent="qa")

    api._widen_citations_from_note(out, "מדרש אגדה, Numbers.22.5.1",
                                   retrieved_refs=["SomeOther.Ref.1"])

    assert out.citations == [], "a real ref outside the retrieved set must not become a citation"
    assert logged and logged[0][0] == "source_note_not_retrieved"
    assert "Numbers.22.5.1" in logged[0][1]["refs"]


def test_a_ref_actually_retrieved_this_turn_still_widens(monkeypatch):
    """The common, correct case: the model named something it was genuinely shown."""
    from types import SimpleNamespace

    monkeypatch.setattr(api, "_fetch_refs", lambda refs: [
        SimpleNamespace(payload={"ref": "Numbers.22.5.1", "text_he": "טקסט"})])
    monkeypatch.setattr(api.db, "record_guard_finding", lambda *a, **k: None)
    out = api.QueryResponse(answer="a", citations=[], grounded=True, intent="qa")

    api._widen_citations_from_note(out, "מדרש אגדה, Numbers.22.5.1",
                                   retrieved_refs=["Numbers.22.5.1", "Other.Ref.2"])

    assert [c.ref for c in out.citations] == ["Numbers.22.5.1"]


def test_no_retrieved_refs_given_falls_back_to_corpus_only(monkeypatch):
    """Call sites that have not threaded retrieved_refs through yet keep the old behaviour —
    this is an additive check, not a breaking one."""
    from types import SimpleNamespace

    monkeypatch.setattr(api, "_fetch_refs", lambda refs: [
        SimpleNamespace(payload={"ref": "Numbers.22.5.1", "text_he": "טקסט"})])
    monkeypatch.setattr(api.db, "record_guard_finding", lambda *a, **k: None)
    out = api.QueryResponse(answer="a", citations=[], grounded=True, intent="qa")

    api._widen_citations_from_note(out, "מדרש אגדה, Numbers.22.5.1")  # no retrieved_refs at all

    assert [c.ref for c in out.citations] == ["Numbers.22.5.1"]


def test_a_widened_citation_gets_its_commentator_derived_from_the_ref(monkeypatch):
    """`commentator_id` is EMPTY on all 2.4M points of the commercial corpus and is recovered at
    read time everywhere else (retrieval/hybrid.py::_to_hit). Reading the payload alone is why a
    widened citation rendered as a bare "Chizkuni,_Deuteronomy.10.6.1" chip next to "rashbam"."""
    from types import SimpleNamespace

    monkeypatch.setattr(api, "_fetch_refs", lambda refs: [
        SimpleNamespace(payload={"ref": "Chizkuni,_Deuteronomy.10.6.1", "text_he": "טקסט"})])
    monkeypatch.setattr(api.db, "record_guard_finding", lambda *a, **k: None)
    out = api.QueryResponse(answer="a", citations=[], grounded=True, intent="qa")

    api._widen_citations_from_note(out, "חזקוני, Chizkuni,_Deuteronomy.10.6.1")

    # commentator_from_ref keys on "_on_", which the comma form does not have — so the chip has to
    # fall back to the Hebrew display name, and that is what must be populated.
    assert out.citations[0].ref_he.startswith("חזקוני")


# ── chavruta mode had no citation-faithfulness guard at all (2026-08-19/20) ───────────────────
# _qa_answer runs enforce_citations AND unverified_quotes; _generate_chavruta_turn ran neither — its
# own bespoke [S#] regex only built the citation list, never checked a claim against what was
# actually retrieved, and `caveats` stayed [] unconditionally. This is exactly the gap that let a
# learner's invented pasuk ("לא ימיש השרימפ מתוך חלבו", a pun) get validated as real, with a made-up
# Mishnah citation, in a real production chat (2026-08-13).
class _FakeChavrutaLLM:
    def __init__(self, raw: str):
        self._raw = raw

    def request(self, job, *, lang, token_budget):
        return self._raw, []


def test_chavruta_turn_flags_a_quote_not_in_the_retrieved_sources():
    hits = [RankedHit(chunk_id="c1", ref="Test.1.1", text="טקסט מקור אמיתי שאינו קשור לציטוט",
                      score=0.9)]
    raw = ('שמעתי אותך. הפסוק "זהו ציטוט מומצא לחלוטין שאינו נמצא בשום מקור שסופק כאן" [S1] '
           'מלמד יסוד חשוב — מה אתה חושב?')
    out = api._generate_chavruta_turn("שאלה", hits, "he", True, [], False, _FakeChavrutaLLM(raw))

    assert out.caveats, "an unverified quote in chavruta mode must produce a caveat, like QA mode does"


def test_chavruta_turn_is_quiet_when_the_quote_is_real():
    real = "טקסט מקור אמיתי שמצוטט נכונה כאן בתשובה"
    hits = [RankedHit(chunk_id="c1", ref="Test.1.1", text=real, score=0.9)]
    raw = f'שמעתי אותך. נאמר: "{real}" [S1] — מה אתה חושב?'
    out = api._generate_chavruta_turn("שאלה", hits, "he", True, [], False, _FakeChavrutaLLM(raw))

    assert out.caveats == []


def test_chavruta_turn_resolves_a_nonstandard_marker_shape():
    """Found live 2026-08-19 (session 11190b1b): the old bespoke regex `\\[\\s*S(\\d+)\\s*\\]`
    missed "[source S1]" outright, silently dropping the citation instead of resolving it."""
    hits = [RankedHit(chunk_id="c1", ref="Test.1.1", text="טקסט", score=0.9)]
    raw = "תשובה קצרה [source S1] בלי הדלפה."
    out = api._generate_chavruta_turn("שאלה", hits, "he", True, [], False, _FakeChavrutaLLM(raw))

    assert [c.ref for c in out.citations] == ["Test.1.1"]


def test_chavruta_job_prompt_now_prohibits_inventing_a_users_own_quote():
    """Before this, the job only ever instructed the model to CITE sources — never told it not to
    validate a fabricated one the LEARNER hands it, which is exactly the shrimp-pasuk failure mode
    (2026-08-13). QA's system prompt already had this prohibition; chavruta's job did not."""
    job = api._chavruta_job_md("שאלה", [], "he", [])
    assert "MUST NOT invent" in job
    assert "the learner is the one who states" in job


# ── license/version_title dropped on the standard QA citation path (found 2026-08-26) ──────────
# Real production bug: a regular chat answer's SourcesPanel attribution (license + edition) showed
# up on SOME source cards and not others, even though the commercial-rights backfill covers the
# whole 2.4M-point collection. Root cause traced live: `Citation` (corpus/schema.py) — the dataclass
# the STANDARD pipeline.ask() / enforce_citations() path uses — never had `license`/`version_title`
# fields at all, so every citation built through it silently lost the data regardless of what the
# underlying RankedHit carried. The lesson source-sheet and source-note-widening paths were fine
# because they build CitationOut directly from RankedHit, bypassing Citation entirely — which is
# exactly why the gap was invisible in the one spot already verified (a finished lesson) and only
# showed up on ordinary qa/explain answers, the highest-traffic path in the app.
from chavruta.generation.grounded import enforce_citations
from chavruta.lessons.builder import _section
from chavruta.lessons.templates import Stage
from chavruta.retrieval.base import RankedHit as _RH


def test_citation_dataclass_carries_license_and_version_title():
    from chavruta.corpus.schema import Citation
    c = Citation(chunk_id="c1", ref="Test.1.1", deep_link="https://x",
                 license="CC-BY-SA", version_title="Wikisource")
    assert c.license == "CC-BY-SA"
    assert c.version_title == "Wikisource"


def test_enforce_citations_carries_license_and_version_title_from_the_hit():
    """The standard pipeline.ask() path (used by ordinary qa/explain answers, not lessons)."""
    hit = _RH(chunk_id="c1", ref="Test.1.1", text="טקסט", score=0.9,
              license="Public Domain", version_title="Vilna Edition")
    text, citations, grounded = enforce_citations("תשובה [S1]", {"S1": hit})
    assert grounded is True
    assert citations[0].license == "Public Domain"
    assert citations[0].version_title == "Vilna Edition"


def test_lesson_builder_section_carries_license_and_version_title():
    hit = _RH(chunk_id="c1", ref="Test.1.1", text="טקסט", score=0.9,
              license="CC0", version_title="ויקיטקסט")
    stage = Stage(key="opening", title_he="פתיחה")
    section = _section(stage, [hit])
    assert section.citations[0].license == "CC0"
    assert section.citations[0].version_title == "ויקיטקסט"


def test_generate_qa_turn_from_hits_passes_license_and_version_title_through(monkeypatch):
    """_generate_qa_turn_from_hits (parsha's default, non-lesson turn) has its own local _cite()
    closure, separate from enforce_citations — it silently dropped license/version_title even when
    the Answer's Citation objects carried them. Exercises the real function end-to-end, not a
    reimplementation of the fix."""
    from chavruta.corpus.schema import Answer, Citation

    hit = _RH(chunk_id="c1", ref="Test.1.1", text="טקסט", score=0.9)
    real_citation = Citation(chunk_id="c1", ref="Test.1.1", deep_link="https://x",
                             license="CC-BY-SA", version_title="Wikisource")
    answer = Answer(text="תשובה [S1]", citations=[real_citation], grounded=True)

    class _FakePipeline:
        llm = "llm"

        def _qa_answer(self, query, result, llm=None, *, history=None, missing_note=None):
            return answer

    monkeypatch.setattr(api, "_get_pipeline", lambda: _FakePipeline())
    resp = api._generate_qa_turn_from_hits("שאלה", [hit], "he", True, [], None)
    assert resp.citations[0].license == "CC-BY-SA"
    assert resp.citations[0].version_title == "Wikisource"


def test_build_lesson_plan_propagates_license_and_version_title():
    from chavruta.generation.grounded import build_lesson_plan
    hit = _RH(chunk_id="c1", ref="Rashi_on_Berakhot.118.17.1", text="טקסט", score=0.9,
              license="Public Domain", version_title="Vilna Edition")
    plan = build_lesson_plan("ברכות", [hit])
    assert plan.sections[0].citations[0].license == "Public Domain"
    assert plan.sections[0].citations[0].version_title == "Vilna Edition"


def test_build_lesson_walkthrough_prompt_propagates_metadata_to_source_blocks():
    from chavruta.corpus.schema import Citation
    from chavruta.generation.grounded import LessonPlan, LessonSection, build_lesson_walkthrough_prompt
    cit = Citation(chunk_id="c1", ref="Rashi_on_Berakhot.118.17.1", quote="טקסט רש\"י",
                   license="Public Domain", version_title="Vilna Edition", deep_link="https://sefaria.org/x")
    plan = LessonPlan(topic="ברכות", sections=[LessonSection(heading="ברכות נט", source_refs=[cit.ref], citations=[cit])])
    prompt, marker_map = build_lesson_walkthrough_prompt(plan, "ברכות", lang="he")
    assert prompt.sources[0].license == "Public Domain"
    assert prompt.sources[0].version_title == "Vilna Edition"
    assert prompt.sources[0].deep_link == "https://sefaria.org/x"


def test_generate_lesson_from_hits_resolves_fallback_license_for_commentator(monkeypatch):
    from types import SimpleNamespace
    from app.api import _generate_lesson_from_hits

    class _FakeLLM:
        def request(self, job, **kw):
            return "=== FULL_LESSON ===\nשיעור [S1]\n=== ORDER ===\nS1", []

    class _FakeProfile:
        collection = "corpus"
        llm_max_tokens = 4096

    class _FakePipeline:
        profile = _FakeProfile()
        llm = _FakeLLM()

    monkeypatch.setattr(api, "_get_pipeline", lambda: _FakePipeline())
    hit = _RH(chunk_id="c1", ref="Rashi_on_Berakhot.118.17.1", text="טקסט", score=0.9,
              license="", version_title="")
    resp = _generate_lesson_from_hits("נושא", [hit], "he", True, audience="general", grade_band="high_school",
                                      length="medium", tpl=None, history=[], owner_id="test", llm=_FakeLLM())
    assert len(resp.citations) == 1
    assert resp.citations[0].license == "Public Domain"
    assert resp.citations[0].version_title == "Vilna Edition"


def test_widen_citations_from_note_resolves_fallback_license(monkeypatch):
    from types import SimpleNamespace
    from app.api import QueryResponse, _widen_citations_from_note

    class _FakeStore:
        def fetch_by_refs(self, coll, refs, **kw):
            return [SimpleNamespace(payload={"ref": "Rashi_on_Berakhot.118.17.1", "text_he": "טקסט"})]

    class _FakePipeline:
        store = _FakeStore()
        profile = SimpleNamespace(collection="corpus")

    monkeypatch.setattr(api, "_get_pipeline", lambda: _FakePipeline())
    resp = QueryResponse(answer="תשובה", citations=[], intent="qa", grounded=True)
    _widen_citations_from_note(resp, "רש\"י — Rashi_on_Berakhot.118.17.1", retrieved_refs=["Rashi_on_Berakhot.118.17.1"])
    assert len(resp.citations) == 1
    assert resp.citations[0].license == "Public Domain"
    assert resp.citations[0].version_title == "Vilna Edition"

