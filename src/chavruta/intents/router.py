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
    """Enriches a Query in place; explicit user choices always win over detection."""

    default_work_ids: list[str] | None = None
    extra_aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def route(self, query: Query) -> Query:
        if not query.lang:
            query.lang = detect_lang(query.text)

        commentators = detect_commentators(query.text)
        if commentators and not query.commentator_ids:
            # Bias, don't hard-filter, when exactly one is named in a compare-less question:
            query.commentator_ids = commentators

        if query.intent is Intent.QA:   # only override the default, never an explicit choice
            query.intent = detect_intent(query.text, len(commentators))

        if query.work_ids is None and self.default_work_ids:
            query.work_ids = list(self.default_work_ids)

        # Comparison/explanation benefits from anchor-chain expansion (supercommentaries).
        if query.intent in (Intent.COMPARE, Intent.LESSON) and not query.expand_links:
            query.expand_links = True

        return query
