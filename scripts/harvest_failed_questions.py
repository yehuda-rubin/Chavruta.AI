"""harvest_failed_questions.py — the questions production already labelled as retrieval failures.

Every answer writes a row to `usage_events` saying whether the retrieval worked: `no_source` means
the system found nothing and said so, `llm_calls > 1` means round one missed and the agentic loop
had to go back for more. Nobody was collecting the QUESTIONS behind those rows, so the most valuable
eval items there are — real failures, already proven reachable — were being thrown away daily.

This pulls them out, ready to be labelled with the refs that SHOULD have surfaced, and appended to
eval/regressions_v1.jsonl. It is also step one of docs/REINFORCEMENT_LEARNING.md 5: the reward
signal for retrieval is "did the right source surface?", and these are the cases where it did not.

PRIVACY — read this before changing anything here
-------------------------------------------------
Conversation text is read through db.reviewable_questions and nowhere else. That function is the
single enforcement point for every promise made to users about this use (not retroactive, per-chat
opt-out, account-wide opt-out, pending deletion). Do NOT hand-roll a query over `messages` to go
faster — the promises live in that function, not in this one.

The account-wide opt-out lives in Supabase user_metadata and cannot be read from the DB, so it is
fetched here and passed in. If Supabase cannot be reached this script STOPS: reviewable_questions
treats an unknown opt-out list as "everyone opted out" and would return nothing, and a silent empty
harvest looks exactly like a clean run.

The output is a LOCAL working file and MUST NOT be committed. eval/ lives in a public repository,
and reading a user's question internally (privacy policy 2) is not the same as publishing it: no
amount of paraphrasing makes someone else's sentence ours to put on GitHub. The default output name
is gitignored for that reason. What goes into an eval set is a row written from scratch describing
the RETRIEVAL PATTERN that failed — "a lesson request naming a sugya colloquially" — never the
sentence a person typed.

    python scripts/harvest_failed_questions.py            # → harvested_failures.jsonl (gitignored)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app.db as db  # noqa: E402  — after the path insert

# usage_events carries no session_id, so a question is tied to its outcome by owner + time. The
# event is written when the request finishes, the message when it arrives, so the event is LATER by
# however long generation took — measured at 49-57s average, with lessons far longer. Six minutes is
# wide enough for a slow lesson and still narrower than the gap between two questions from the same
# person in practice.
MATCH_WINDOW_S = 360


def _opted_out_owners() -> set[str]:
    """Owner ids whose account-wide opt-out is set. Raises rather than returning a guess."""
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    if not (key and url):
        raise SystemExit("no Supabase credentials — cannot establish who opted out, so cannot read "
                         "anything. This is the fail-closed path, not an error to work around.")
    out: set[str] = set()
    page = 1
    while True:
        req = urllib.request.Request(f"{url}/auth/v1/admin/users?page={page}&per_page=1000",
                                     headers={"Authorization": f"Bearer {key}", "apikey": key})
        with urllib.request.urlopen(req, timeout=15) as resp:
            users = json.loads(resp.read()).get("users", [])
        for u in users:
            if (u.get("user_metadata") or {}).get("data_review_opt_out"):
                out.add(u["id"])
        if len(users) < 1000:
            return out
        page += 1


def _ts(value: str | None) -> float:
    """ISO → epoch seconds, tolerant of the mix of naive and offset-aware strings in the DB."""
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return 0.0


def _outcomes() -> list[dict]:
    with db._LOCK:
        rows = db.get_conn().execute(
            "SELECT at, owner_id, intent, grounded, no_source, llm_calls, citations "
            "FROM usage_events WHERE owner_id IS NOT NULL ORDER BY at").fetchall()
    return [dict(r) | {"_t": _ts(r["at"])} for r in rows]


def _known_questions() -> set[str]:
    """Normalised text of every question already in an eval set — harvesting a duplicate wastes a
    labelling decision that was already made."""
    seen: set[str] = set()
    for path in [ROOT / "eval" / "regressions_v1.jsonl", ROOT / "tests" / "eval" / "indirect_questions.jsonl"]:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            row = json.loads(line)
            text = row.get("question") or row.get("q") or ""
            seen.add(" ".join(text.split()))
    return seen


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="harvested_failures.jsonl")
    ap.add_argument("--limit", type=int, default=1000, help="questions to consider")
    ap.add_argument("--include-passes", action="store_true",
                    help="also emit questions whose retrieval worked (for a control set)")
    args = ap.parse_args()

    opted_out = _opted_out_owners()
    print(f"{len(opted_out)} account(s) opted out of review", file=sys.stderr)

    questions = db.reviewable_questions(limit=args.limit, opted_out_owners=opted_out)
    print(f"{len(questions)} question(s) inside the review gate", file=sys.stderr)
    if not questions:
        print("nothing to harvest — either no traffic since the effective date, or all excluded",
              file=sys.stderr)
        return 0

    events = _outcomes()
    known = _known_questions()

    # Prior user turns in the same chat, so a follow-up ("תנסה", "למה?") carries the topic it is
    # following up on. Without this those rows are unusable: the question alone has no content.
    by_session: dict[str, list[dict]] = {}
    for q in questions:
        by_session.setdefault(q["session_id"], []).append(q)

    harvested, skipped_dupe, unmatched = [], 0, 0
    for q in questions:
        qt = _ts(q["created_at"])
        near = [e for e in events
                if e["owner_id"] == q["owner_id"] and 0 <= e["_t"] - qt <= MATCH_WINDOW_S]
        if not near:
            unmatched += 1
            continue
        ev = min(near, key=lambda e: e["_t"] - qt)
        failed = bool(ev["no_source"]) or (ev["llm_calls"] or 0) > 1
        if not failed and not args.include_passes:
            continue
        text = " ".join(q["text"].split())
        if text in known:
            skipped_dupe += 1
            continue
        known.add(text)

        history = [" ".join(p["text"].split())
                   for p in by_session.get(q["session_id"], []) if p["id"] < q["id"]]
        why = ("honest no-source" if ev["no_source"]
               else f"round one missed, {ev['llm_calls']} LLM calls")
        harvested.append({
            "qid": f"harvest-{q['created_at'][:10]}-{q['id']}",
            "question": text,
            "lang": "he",
            "expected_refs": [],            # ← TO LABEL. [] currently reads as "no-source is correct"
            "intent": ev["intent"] or q.get("intent") or "qa",
            **({"history": history} if history else {}),
            "note": f"{q['created_at'][:10]} production: {why}; "
                    f"grounded={ev['grounded']} citations={ev['citations']}. UNLABELLED.",
        })

    Path(args.out).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in harvested) + "\n", encoding="utf-8")
    print(f"\n{len(harvested)} failure(s) written to {args.out}"
          f"  ({skipped_dupe} already in an eval set, {unmatched} with no matching event)",
          file=sys.stderr)
    print("expected_refs is EMPTY on every row and an empty list MEANS 'no-source is the right "
          "answer' to the harness — label them before use.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
