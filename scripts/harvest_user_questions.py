"""Add up to N real user questions a day to the human-written eval set.

WHY
---
The mechanically harvested pairs (scripts/harvest_pairs.py) are written in rabbinic Hebrew, because
they are rabbinic Hebrew. Real users write modern colloquial Hebrew, and the gap between the two is
the measured failure — the same chunk ranked #2 for a source-language query and outside the top 50
for a human phrasing of the same question. No amount of corpus-derived data closes that, because the
corpus does not contain modern colloquial Hebrew. Real questions are the only correct distribution
we will ever have, so they are worth collecting slowly and permanently.

Deliberately a TRICKLE — a few a day, skipping days with nothing new. The eval set is meant to be
read and curated by a person: expected_refs are left EMPTY here because only a human can say what
the right answer was. An unlabelled question is still useful (it can be run and eyeballed), and a
wrongly-labelled one is worse than none, since it would silently punish a retriever for being right.

PRIVACY
-------
Everything this reads goes through db.reviewable_questions, the single sanctioned gate. It enforces
all three promises made to users in the 2026-08-10 notice: not retroactive, per-chat opt-out, and
account-wide opt-out. Do not query `messages` directly here — that gate exists so these conditions
live in exactly one place.

The account-wide opt-out lives in Supabase user_metadata, which this script cannot read on its own.
It therefore takes the opted-out owner ids as input and passes them through. With no way to
establish them it passes None, and the gate returns NOTHING rather than assuming nobody opted out:
a privacy gate that fails open is not a gate.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import app.db as db  # noqa: E402

DEFAULT_OUT = "eval/user_questions_v1.jsonl"
STATE_FILE = "eval/.user_questions_state.json"   # last message id taken, so days don't re-take

# A question worth adding has to be a QUESTION. These are the shapes that are not:
_MIN_CHARS = 12
_MAX_CHARS = 400          # a pasted daf is not a question about one
_SKIP_PATTERNS = (
    re.compile(r"^\s*(תנסה|נסה|עוד|המשך|כן|לא|תודה|אוקיי|ok|thanks?)\s*[.!?]?\s*$", re.I),
)


def _is_useful(text: str) -> bool:
    """Whether a turn is a real, self-contained question rather than conversational glue.

    Follow-ups like "תנסה" or "עוד" are excluded not because they are unimportant — one of them
    exposed a real bug — but because as an EVAL ITEM they are meaningless in isolation: run on their
    own they have no answer to be right or wrong about.
    """
    t = (text or "").strip()
    if not (_MIN_CHARS <= len(t) <= _MAX_CHARS):
        return False
    return not any(p.match(t) for p in _SKIP_PATTERNS)


def _load_state(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return int(json.loads(path.read_text(encoding="utf-8")).get("last_message_id", 0))
    except (ValueError, OSError):
        return 0


def _existing_questions(out: Path) -> set[str]:
    """Questions already in the file, so a rephrasing of the same thing is not added twice."""
    if not out.exists():
        return set()
    seen = set()
    for line in out.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        try:
            seen.add(json.loads(line).get("question", "").strip())
        except ValueError:
            continue
    return seen


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--limit", type=int, default=3, help="max questions to add in one run")
    ap.add_argument("--opted-out", default="",
                    help="comma-separated owner ids with the ACCOUNT-WIDE opt-out set. Pass "
                         "--opted-out-unknown if you cannot establish them.")
    ap.add_argument("--opted-out-unknown", action="store_true",
                    help="the account-wide opt-out list could not be read — take nothing at all")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    out = ROOT / args.out
    state_path = ROOT / STATE_FILE
    last_id = _load_state(state_path)

    opted_out = None if args.opted_out_unknown else \
        {o.strip() for o in args.opted_out.split(",") if o.strip()}
    rows = db.reviewable_questions(limit=500, opted_out_owners=opted_out)
    if opted_out is None:
        print("account-wide opt-outs unknown → took nothing (the gate fails closed, by design)")
        return 0

    seen = _existing_questions(out)
    picked: list[dict] = []
    for r in rows:
        if r["id"] <= last_id:
            continue
        text = (r["text"] or "").strip()
        if not _is_useful(text) or text in seen:
            continue
        seen.add(text)
        picked.append({
            "id": f"uq-{r['id']}",
            "question": text,
            "intent": r["intent"] or "qa",
            # EMPTY on purpose — a human labels what the right sources were. A guessed label would
            # punish the retriever for being right, which is worse than having no label at all.
            "expected_refs": [],
            "asked_at": r["created_at"],
            "needs_labelling": True,
        })
        if len(picked) >= max(1, args.limit):
            break

    if not picked:
        print("no new questions today — nothing added")
        return 0

    if args.dry_run:
        for p in picked:
            print(f"  would add {p['id']}: {p['question'][:70]}")
        return 0

    new_last = max(int(p["id"].split("-")[1]) for p in picked)
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            "# Chavruta.AI — REAL user questions, added a few a day by\n"
            "# scripts/harvest_user_questions.py under the 2026-08-10 review permission.\n"
            "# expected_refs is EMPTY until a human labels it — see needs_labelling.\n"
            "# This is the only eval set in the true (modern, colloquial) question distribution,\n"
            "# which is why it is the VETO set for retrieval tuning and never merely averaged in.\n",
            encoding="utf-8")
    with out.open("a", encoding="utf-8") as fh:
        for p in picked:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    state_path.write_text(json.dumps({"last_message_id": new_last}), encoding="utf-8")

    print(f"added {len(picked)} question(s) → {out}")
    for p in picked:
        print(f"   {p['id']}: {p['question'][:70]}")
    print(f"{sum(1 for p in picked if p['needs_labelling'])} awaiting expected_refs labelling")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
