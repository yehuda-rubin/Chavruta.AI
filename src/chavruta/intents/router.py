"""Intent + language routing (task T025) — capability routing for the pipeline.

Detects: question language (he/en), intent (qa | explain | compare | lesson; halacha
reserved), named commentators (biases retrieval), and named refs. Pure heuristics — cheap,
offline, deterministic. The router only *enriches* the Query; grounding stays in the
pipeline/generation layer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from chavruta.corpus.schema import Intent, Query
from chavruta.intents.hebrew_refs import detect_hebrew_refs
from chavruta.intents.landmarks import resolve_landmarks

# ── Commentator aliases (extendable as data; mirrors the corpus commentator ids) ──
COMMENTATOR_ALIASES: dict[str, tuple[str, ...]] = {
    "rashi": ("rashi", "רש\"י", "רשי", "רש״י"),
    "ramban": ("ramban", "nachmanides", "רמב\"ן", "רמבן", "רמב״ן"),
    "ibn_ezra": ("ibn ezra", "אבן עזרא", "ראב\"ע", "ראב״ע"),
    "radak": ("radak", "רד\"ק", "רדק", "רד״ק"),
    "sforno": ("sforno", "ספורנו"),
    "rashbam": ("rashbam", "רשב\"ם", "רשב״ם", "רשבם"),
    "or_hachaim": ("or hachaim", "אור החיים"),
    "malbim": ("malbim", "מלבי\"ם", "מלבי״ם", "מלבים"),
    "metzudat_david": ("metzudat david", "מצודת דוד"),
    "metzudat_zion": ("metzudat zion", "מצודת ציון"),
    "onkelos": ("onkelos", "אונקלוס"),
    "targum_jonathan": ("targum jonathan", "תרגום יונתן"),
}

# Known bodies of work users ask about by name. Detecting an explicit mention lets the
# pipeline answer honestly when that work is not loaded (Principle I — the spec's
# "out-of-corpus question" edge case), instead of returning merely-similar Tanakh hits.
WORK_ALIASES: dict[str, tuple[str, ...]] = {
    "tanakh": ("tanakh", "tanach", "תנ\"ך", "תנך", "תנ״ך", "מקרא"),
    "mishnah": ("mishnah", "mishna", "משנה", "מסכת"),
    "talmud": ("talmud", "gemara", "גמרא", "תלמוד", "בבלי", "ירושלמי"),
    "shulchan_aruch": ("shulchan aruch", "שולחן ערוך", "שו\"ע", "שו״ע"),
    # Responsa (שו"ת) — unambiguous terms only; bare "תשובה" means repentance, not a teshuva.
    "responsa": ("responsa", "teshuvot", "שו\"ת", "שו״ת", "שאלות ותשובות"),
    "tur": ("the tur", "טור "),
    "mishneh_torah": ("mishneh torah", "משנה תורה", "rambam", 'הרמב"ם במשנה'),
    "zohar": ("zohar", "זוהר", "הזוהר"),
    "mishnah_berurah": ("mishnah berurah", "משנה ברורה"),
    "midrash": ("midrash", "מדרש"),
    # planned supercommentaries (loaded later via the registry — D11)
    "mizrachi": ("mizrachi", "המזרחי", "מזרחי"),
    "gur_aryeh": ("gur aryeh", "גור אריה"),
    "sifsei_chachamim": ("sifsei chachamim", "שפתי חכמים"),
    # modern works (not on the ingestion roadmap; honesty still applies)
    "modern_torah": ("soloveitchik", "סולוביצ'יק", "halakhic man", "rav kook", 'הראי"ה קוק'),
}

# English book names as they appear in the corpus ref scheme ("Genesis.1.3")
_BOOKS = (
    "Genesis|Exodus|Leviticus|Numbers|Deuteronomy|Joshua|Judges|I Samuel|II Samuel|"
    "I Kings|II Kings|Isaiah|Jeremiah|Ezekiel|Hosea|Joel|Amos|Obadiah|Jonah|Micah|"
    "Nahum|Habakkuk|Zephaniah|Haggai|Zechariah|Malachi|Psalms|Proverbs|Job|"
    "Song of Songs|Ruth|Lamentations|Ecclesiastes|Esther|Daniel|Ezra|Nehemiah|"
    "I Chronicles|II Chronicles"
)
_REF_PAT = re.compile(rf"\b({_BOOKS})\s+(\d+)(?:[:.](\d+))?", re.IGNORECASE)
_BOOK_CANON = {b.lower(): b for b in _BOOKS.split("|")}

_LESSON_PAT = re.compile(
    r"\b(prepare|build|create|make)\b.*\b(lesson|shiur|class)\b"
    r"|שיעור|הכן\s+שיעור|תכין\s+שיעור|בנה\s+שיעור", re.IGNORECASE)
_COMPARE_PAT = re.compile(
    r"\b(differ|difference|disagree|compare|versus|vs\.?)\b"
    r"|מחלוקת|הבדל|השווה|חולק|לעומת", re.IGNORECASE)
_EXPLAIN_PAT = re.compile(
    r"\b(explain|meaning of|what does .* mean)\b"
    r"|הסבר|תסביר|באר|פרש\s|מה\s+הפירוש", re.IGNORECASE)
_HALACHA_PAT = re.compile(
    r"\b(halacha|halakha|is it permitted|is it forbidden|may i|allowed to)\b"
    r"|הלכה|מותר|אסור|האם\s+מותר|האם\s+אסור|מה\s+הדין", re.IGNORECASE)


# Lesson/prepare lead-ins to strip from the RETRIEVAL text (they pollute the embedding;
# the intent is already known). The related-material breadth itself is desirable — this
# only sharpens the central match so the sugya's core source surfaces for the opening.
_LESSON_LEAD_HE = re.compile(r"^\s*(?:הכן|תכין|תכנן|בנה|הכנת|הכינו|תכינו)?\s*שיעור\s*(?:על|בנושא|של|ב)?\s*")
_LESSON_LEAD_EN = re.compile(
    r"^\s*(?:please\s+)?(?:prepare|build|make|create|give\s+me)?\s*(?:an?\s+)?"
    r"(?:lesson|shiur|class|source\s*sheet)\s+(?:on|about|for)?\s*", re.IGNORECASE)


def retrieval_text(text: str) -> str:
    """Strip lesson/prepare lead-ins so retrieval embeds the topic, not the instruction."""
    t = _LESSON_LEAD_EN.sub("", _LESSON_LEAD_HE.sub("", text)).strip()
    return t or text


def detect_lang(text: str) -> str:
    """Hebrew if Hebrew letters dominate the alphabetic content, else English."""
    he = sum(1 for ch in text if "א" <= ch <= "ת")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    return "he" if he >= latin else "en"


def detect_commentators(text: str) -> list[str]:
    low = text.lower()
    found = []
    for cid, aliases in COMMENTATOR_ALIASES.items():
        if any(a in low or a in text for a in aliases):
            found.append(cid)
    return found


def detect_requested_works(text: str) -> list[str]:
    """Which bodies of work does the question explicitly name? (e.g. 'מה אומרת המשנה…')"""
    low = text.lower()
    found = []
    for work_id, aliases in WORK_ALIASES.items():
        if any(a in low or a in text for a in aliases):
            found.append(work_id)
    return found


def detect_refs(text: str) -> list[str]:
    """Detect explicit verse refs ('Genesis 1:1' / 'Genesis 1.3') → corpus format 'Genesis.1.1'.

    A chapter-only mention ('Genesis 1') yields 'Genesis.1' (chapter-level anchor).
    """
    refs = []
    for m in _REF_PAT.finditer(text):
        book = _BOOK_CANON.get(m.group(1).lower(), m.group(1).title())
        ref = f"{book}.{m.group(2)}" + (f".{m.group(3)}" if m.group(3) else "")
        if ref not in refs:
            refs.append(ref)
    return refs


def detect_intent(text: str, n_commentators: int) -> Intent:
    if _LESSON_PAT.search(text):
        return Intent.LESSON
    if _HALACHA_PAT.search(text):
        return Intent.HALACHA          # reserved; pipeline treats as qa + caveat until corpus
    if n_commentators >= 2 and _COMPARE_PAT.search(text):
        return Intent.COMPARE
    if _EXPLAIN_PAT.search(text) or n_commentators == 1:
        return Intent.EXPLAIN
    return Intent.QA


@dataclass
class Router:
    """Enriches a Query in place; explicit user choices always win over detection.

    `planner` is an optional LLM fallback (Phase 5) with a `.plan(text) -> dict` method;
    when set, it runs ONLY if the heuristics resolved no explicit ref, and never breaks
    the request (its failures are swallowed). Default None keeps routing offline.
    """

    default_work_ids: list[str] | None = None
    extra_aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)
    planner: object | None = None

    def route(self, query: Query) -> Query:
        if not query.lang:
            query.lang = detect_lang(query.text)

        if not query.search_text:
            query.search_text = retrieval_text(query.text)

        commentators = detect_commentators(query.text)
        if commentators and not query.commentator_ids:
            # Bias, don't hard-filter, when exactly one is named in a compare-less question:
            query.commentator_ids = commentators

        if query.named_refs is None:
            # English explicit refs + Hebrew explicit refs + indirect landmarks.
            refs: list[str] = []
            for r in (*detect_refs(query.text),
                      *detect_hebrew_refs(query.text),
                      *resolve_landmarks(query.text)):
                if r not in refs:
                    refs.append(r)
            if refs:
                query.named_refs = refs

        if query.requested_works is None:
            works = detect_requested_works(query.text)
            if works:
                query.requested_works = works

        if query.intent is Intent.QA:   # only override the default, never an explicit choice
            query.intent = detect_intent(query.text, len(commentators))

        # Optional LLM fallback — only when the heuristics resolved no explicit ref.
        if self.planner is not None and not query.named_refs:
            try:
                hints = self.planner.plan(query.text)
            except Exception:
                hints = {}
            if hints.get("refs"):
                query.named_refs = list(hints["refs"])
            if hints.get("commentators") and not query.commentator_ids:
                query.commentator_ids = list(hints["commentators"])
            if hints.get("intent") and query.intent is Intent.QA:
                try:
                    query.intent = Intent(hints["intent"])
                except ValueError:
                    pass

        if query.work_ids is None and self.default_work_ids:
            query.work_ids = list(self.default_work_ids)

        # Comparison/lesson/responsa benefit from anchor-chain expansion (supercommentaries,
        # poskim-on-the-source) — pull the connected meforshim of each source.
        if query.intent in (Intent.COMPARE, Intent.LESSON, Intent.HALACHA) and not query.expand_links:
            query.expand_links = True
            # depth 2 reaches commentary-on-commentary: pasuk → Rashi → Mizrachi (T033a);
            # for lessons it spans the chain of transmission across loaded corpora (T036a).
            query.expand_depth = max(query.expand_depth, 2)

        return query
