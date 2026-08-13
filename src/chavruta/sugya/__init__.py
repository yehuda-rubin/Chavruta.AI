"""The sugya game — a guided path through one sugya, one source per level.

Design and the reasoning behind it: `docs/SUGYA_GAME.md`. Inspired by the Natural Number Game
(Lean 4), whose actual mechanism — not its theme — is what transfers: the state is always visible,
one new tool per level, and **you may only use what you have already unlocked**. That last rule is
not a metaphor here. A yeshiva has exactly the same one and never writes it down: you cannot quote
Tosafot before you have read him.

THE LINE THIS MODULE WILL NOT CROSS
-----------------------------------
There is no compiler for understanding, and this must never pretend otherwise. Whether a learner
understood Rashi correctly is not machine-decidable, and a sugya has no single truth value for one
to decide. What IS decidable, exactly, is PROVENANCE: is the passage they brought really that
source, and are the words they quoted really in it. So a level never asks "did you understand?" —
it asks "bring the source", and that is checked to the letter.

Understanding is what the chavruta mode is for. It is not scored here, and nothing in this module
returns a judgement about a person's learning.

NO SCORE, NO FAILURE
--------------------
A wrong answer comes back with what was wrong and the level stays open, the way a Lean proof does
not "fail" — it simply has not closed yet. There is no points table and no streak, deliberately
(docs/SUGYA_GAME.md 1): the tight loop is the reward, and badges would be the wrong register for
this material.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).parent / "data"


class SugyaNotFound(KeyError):
    """No curated sugya with that id."""


class LevelNotFound(KeyError):
    """No level with that id inside this sugya."""


@dataclass(frozen=True)
class Level:
    id: str
    title_he: str
    move_he: str            # the "tactic": בירור / דיוק / קושיא / תירוץ / השוואה
    goal_he: str
    hint_he: str
    unlocks_ref: str        # enters the inventory once solved, and stays for every later level
    accept_refs: tuple[str, ...]
    teach_he: str           # shown AFTER a correct answer — the point of the level, not a hint


@dataclass(frozen=True)
class Sugya:
    id: str
    title_he: str
    source_he: str
    intro_he: str
    levels: tuple[Level, ...]

    def level(self, level_id: str) -> Level:
        for lv in self.levels:
            if lv.id == level_id:
                return lv
        raise LevelNotFound(level_id)

    def inventory_at(self, level_id: str) -> tuple[str, ...]:
        """Refs unlocked BEFORE this level — what the learner may already lean on.

        Everything earlier, nothing later. This is the rule the whole design rests on, so it is
        computed from the level order rather than stored anywhere that could drift out of step.
        """
        out: list[str] = []
        for lv in self.levels:
            if lv.id == level_id:
                return tuple(out)
            out.append(lv.unlocks_ref)
        raise LevelNotFound(level_id)


def _parse(raw: dict[str, Any]) -> Sugya:
    return Sugya(
        id=raw["id"], title_he=raw["title_he"], source_he=raw.get("source_he", ""),
        intro_he=raw.get("intro_he", ""),
        levels=tuple(
            Level(id=lv["id"], title_he=lv["title_he"], move_he=lv.get("move_he", ""),
                  goal_he=lv["goal_he"], hint_he=lv.get("hint_he", ""),
                  unlocks_ref=lv["unlocks_ref"],
                  accept_refs=tuple(lv["accept_refs"]), teach_he=lv.get("teach_he", ""))
            for lv in raw["levels"]),
    )


@cache
def load(sugya_id: str) -> Sugya:
    """One curated sugya. Cached — these files are read-only content, not state."""
    path = DATA_DIR / f"{sugya_id}.json"
    # Guard the path rather than trusting the id: this reaches an HTTP route, and `../../etc` in a
    # path segment is the oldest trick there is. Comparing resolved parents is what actually stops
    # it — a substring check on the id would not.
    if path.resolve().parent != DATA_DIR.resolve() or not path.is_file():
        raise SugyaNotFound(sugya_id)
    return _parse(json.loads(path.read_text(encoding="utf-8")))


def available() -> list[dict[str, str]]:
    """Every curated sugya, for a menu. Sorted so the order is stable between calls."""
    out = []
    for p in sorted(DATA_DIR.glob("*.json")):
        try:
            s = load(p.stem)
        except Exception:                   # noqa: BLE001 — one broken file must not hide the rest
            continue
        out.append({"id": s.id, "title_he": s.title_he, "source_he": s.source_he,
                    "levels": str(len(s.levels))})
    return out


# ── Checking an answer ────────────────────────────────────────────────────────
@dataclass(frozen=True)
class CheckResult:
    """`correct` is the only field a caller should branch on for pass/fail; `status` says WHY, which
    is what the learner actually needs to see."""

    correct: bool
    status: str          # correct | wrong_source | not_in_source | unknown_ref | no_answer
    message_he: str
    unlocked_ref: str = ""      # set only on a correct answer


def _skeleton(s: str) -> str:
    """Hebrew letters only — the comparison used for quotes, so niqqud, punctuation and spacing
    cannot make a faithful quote look fabricated. Mirrors generation/grounded.py's approach."""
    return "".join(ch for ch in (s or "") if "א" <= ch <= "ת")


def check(sugya: Sugya, level_id: str, ref: str, quote: str = "", *,
          fetch: Callable[[Iterable[str]], list[Any]] | None = None) -> CheckResult:
    """Was the right source brought, and does it really say what was quoted from it?

    `fetch(refs) -> hits` is injected rather than imported: nothing under src/chavruta may depend on
    the web layer, and this has to stay runnable in tests with no Qdrant at all. Without a fetcher
    the ref is still checked against the level — only the quote check is skipped, because a quote
    cannot be verified against a corpus nobody handed us.
    """
    level = sugya.level(level_id)
    ref = (ref or "").strip()
    if not ref:
        return CheckResult(False, "no_answer", "לא נבחר מקור.")

    if ref not in level.accept_refs:
        # Distinguish "a real source, wrong one" from "no such source" — they are different mistakes
        # and deserve different words. Without a fetcher we cannot tell, so we say the safer thing.
        exists = True
        if fetch is not None:
            try:
                exists = bool(fetch([ref]))
            except Exception:               # noqa: BLE001 — a lookup failure is not the learner's error
                exists = True
        if not exists:
            return CheckResult(False, "unknown_ref",
                               "לא מצאתי מקור כזה במאגר. בדוק את ההפניה.")
        return CheckResult(False, "wrong_source",
                           "זה מקור אמיתי, אבל לא זה שהשלב מבקש. קרא שוב את המטרה.")

    # The right source. If they also quoted from it, the quote has to actually be there — this is
    # the mistake a person makes when they remember a source instead of opening it, and the one a
    # teacher in a class of thirty cannot catch.
    if quote.strip() and fetch is not None:
        needle = _skeleton(quote)
        if len(needle) >= 8:
            try:
                hits = fetch([ref])
            except Exception:               # noqa: BLE001
                hits = []
            hay = "".join(_skeleton(_text_of(h)) for h in hits)
            if hay and needle not in hay:
                return CheckResult(False, "not_in_source",
                                   "המקור נכון, אבל המילים שציטטת לא נמצאות בו. פתח אותו וקרא שוב.")

    return CheckResult(True, "correct", level.teach_he or "נכון.", unlocked_ref=level.unlocks_ref)


def _text_of(hit: Any) -> str:
    """The Hebrew of a hit, whatever shape the store handed back (payload dict, object, or plain)."""
    payload = getattr(hit, "payload", None)
    if isinstance(payload, dict):
        return payload.get("text_he") or payload.get("text") or ""
    if isinstance(hit, dict):
        return hit.get("text_he") or hit.get("text") or ""
    return getattr(hit, "text_he", "") or getattr(hit, "text", "") or ""
