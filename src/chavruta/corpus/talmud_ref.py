"""Talmud daf-reference shifting — fix the corpus-wide off-by-one daf labelling.

The Talmud ingest mislabelled every daf: corpus ref `Bava Metzia.3a.1` actually holds
the text of real `Bava Metzia.2a.1` ("שניים אוחזין"). The content + vectors are correct;
only the daf NUMBER in the ref is +1. `shift_daf(ref, -1)` corrects a single ref by
decrementing its daf, leaving the amud, segment, book, and any commentator prefix intact.

A Talmud daf ref has a single dotted component matching `<digits><a|b>` (e.g. "3a").
Tanakh ("Genesis.1.1") and Mishnah ("Mishnah Bava Metzia.1.1") refs have no such
component and are returned unchanged — so this is safe to run over any ref.
"""

from __future__ import annotations

import re

_DAF_COMPONENT = re.compile(r"^(\d+)([ab])$")


def daf_component(ref: str) -> int | None:
    """Index of the dotted component that is a daf (e.g. '3a'), or None if the ref has none."""
    for i, part in enumerate(ref.split(".")):
        if _DAF_COMPONENT.match(part):
            return i
    return None


def shift_daf(ref: str, delta: int = -1) -> str:
    """Return `ref` with its daf number shifted by `delta` (default −1).

    Non-Talmud refs (no `<n><a|b>` component) are returned unchanged. A shift that would
    drop the daf below 2 is refused (returns the ref unchanged) — daf 1 does not exist.
    """
    parts = ref.split(".")
    idx = daf_component(ref)
    if idx is None:
        return ref
    m = _DAF_COMPONENT.match(parts[idx])
    daf = int(m.group(1)) + delta
    if daf < 2:
        return ref
    parts[idx] = f"{daf}{m.group(2)}"
    return ".".join(parts)
