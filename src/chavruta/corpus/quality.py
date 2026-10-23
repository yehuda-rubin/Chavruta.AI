"""Chunks that are in the corpus but carry no text worth citing.

The full Hebrew-Wikisource scan (`ws:` layer, scripts/modal_full_torah_wikisource_ingest.py) chunked
every page under a kept title, including a book's index page. "רש"י מנוקד על המקרא/ספר בראשית" became a
chunk of 136 lines and 150 words, all of them "פרשת נח", "פרק ז" and the like, and it was served as
source 1 of a lesson's source sheet. Such a chunk has no content, so it is dropped at retrieval rather
than rewritten in the on-disk collection.
"""

from __future__ import annotations

import re

# A line that is only a heading: a structural word, then at most a few tokens (the number or name).
_HEADING = re.compile(
    r"^(פרק|פרקים|פרשת|פרשה|סימן|סימנים|דף|הלכות|הלכה|חלק|ספר|שער|מאמר|אות|משנה|מסכת|מזמור|תוכן|"
    r"chapter|part|book|section|siman|parashat)\b",
    re.IGNORECASE,
)
_MIN_LINES = 8           # a handful of headings can open a real passage; an index runs on
_MAX_WORDS_PER_LINE = 3  # prose and even poetry average well above this
_MIN_HEADING_SHARE = 0.6


def is_index_page(text: str | None) -> bool:
    """True when the text is a table of contents: many short lines, mostly bare headings."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) < _MIN_LINES:
        return False
    if sum(len(ln.split()) for ln in lines) / len(lines) > _MAX_WORDS_PER_LINE:
        return False
    headings = sum(1 for ln in lines if _HEADING.match(ln))
    return headings / len(lines) >= _MIN_HEADING_SHARE
