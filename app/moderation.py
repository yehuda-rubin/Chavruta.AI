"""Heuristic content-safety scan over saved messages — keyword/pattern based, NOT an LLM call.

Cheap and always-on, but coarse by nature: expect both false positives and false negatives. A hit
is a candidate for HUMAN review (written to `message_reports` with source='auto', reviewed via
`scripts/moderation_report.py`) — it never blocks, deletes, or auto-replies to anything. Tune the
keyword lists below as real hits show what's actually noisy or actually missed; this is meant to be
read and edited, not treated as a trained classifier.

Two categories, matching the two risks this product has already identified:

  illegal_or_abusive — the message (usually the user's own question) asks for or contains something
                       seriously harmful: violence, weapons/explosives instructions, CSAM, self-harm
                       encouragement, hate speech, illegal-activity instructions.
  defamation_risk    — the message (usually an answer) makes an accusatory claim that could
                       mischaracterize a real, named person — the risk
                       docs/legal/LAWSUIT-EXPOSURE-2026-07-30.md Finding C already tracks via
                       user self-reports; this is the proactive half.

  A real "is this actually about a specific real person" check needs language understanding this
  module deliberately does not attempt (Hebrew has no letter-casing to spot proper nouns with, and
  an LLM call per message is the more accurate but non-free alternative this project chose NOT to
  use here). So defamation_risk fires on the accusatory keyword alone, with more false positives
  than a name-aware check would have — acceptable because every hit only ever reaches a human
  reviewer, never an automated action.
"""

from __future__ import annotations

import re

_ILLEGAL_OR_ABUSIVE: dict[str, list[str]] = {
    "weapons_explosives": [
        "how to make a bomb", "build a bomb", "מתכון לפצצה", "איך מכינים חומר נפץ",
        "homemade explosive", "חומר נפץ ביתי", "3d printed gun", "אקדח מודפס",
    ],
    "csam": [
        "child porn", "פורנוגרפיית ילדים", "sexual content involving a minor",
        "תוכן מיני עם קטין", "nude photos of a child", "תמונות עירום של ילד",
    ],
    "self_harm": [
        "how to kill myself", "איך להתאבד", "ways to commit suicide", "דרכים להתאבד",
        "how to self harm", "איך לפגוע בעצמי",
    ],
    "hate_violence": [
        "kill all", "לחסל את כל ה", "exterminate the", "genocide against",
        "רצח עם נגד", "call for violence against",
    ],
    "illegal_instructions": [
        "how to synthesize meth", "סינתזה של סמים", "how to hack into", "איך לפרוץ ל",
        "credit card fraud tutorial", "מדריך לרמאות בכרטיס אשראי",
    ],
}

_DEFAMATION_ACCUSATORY: list[str] = [
    "רוצח", "אנס", "גנב", "נוכל", "פדופיל", "כופר", "בוגד", "עבריין מין", "רמאי מועד",
    "murderer", "rapist", "pedophile", "convicted fraud", "child abuser", "war criminal",
]

_HEBREW_CHAR = re.compile(r"[֐-׿]")


def _compile(term: str) -> re.Pattern:
    # Hebrew glues single-letter prefixes (ו/ה/ב/כ/ל/מ/ש) straight onto the next word with no
    # space — "כרוצח", "וגנב" — so a strict \b...\b boundary misses exactly the inflected forms
    # real text actually uses. English text reliably separates words with whitespace/punctuation,
    # so \b there still earns its keep (rejects "murdermystery" matching "murder").
    if _HEBREW_CHAR.search(term):
        return re.compile(re.escape(term))
    return re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)


_COMPILED: dict[str, list[re.Pattern]] = {
    category: [_compile(term) for term in terms]
    for category, terms in _ILLEGAL_OR_ABUSIVE.items()
}
_DEFAMATION_COMPILED = [_compile(term) for term in _DEFAMATION_ACCUSATORY]


def scan(text: str) -> list[str]:
    """Return the matched category tags for this text (empty list = nothing flagged).

    A message can match more than one category; each becomes its own message_reports row so a
    reviewer sees exactly what triggered rather than a merged, harder-to-triage label.
    """
    if not text:
        return []
    hits = [category for category, patterns in _COMPILED.items()
            if any(p.search(text) for p in patterns)]
    if any(p.search(text) for p in _DEFAMATION_COMPILED):
        hits.append("defamation_risk")
    return hits
