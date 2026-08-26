#!/usr/bin/env python3
"""backfill_message_citation_rights.py — fill in license/version_title on citations already stored
in old chat messages / saved lessons, generated before app/api.py's `_cite()` helpers learned to
carry those fields through (fix commit 8b7891b, 2026-08-26 — see tests/unit/test_bug_regressions.py
for the root cause). A message generated before that fix has its citations JSON permanently missing
license/version_title, since it's stored once at generation time and just replayed on every read —
the code fix alone only helps NEW answers, which is exactly why "it works in new chats, not old
ones" (reported live 2026-08-26).

WHY A BACKFILL HERE, UNLIKE THE 2.4M-POINT QDRANT COLLECTION
    scripts/backfill_commercial_rights.py deliberately did NOT try to derive commentator_id/anchor_ref
    at write time — those are cheap to derive at READ time from the ref string instead, because a
    real Qdrant backfill against the on-disk collection was measured at ~5 points/sec (days). This is
    a completely different scale: a few hundred SQLite rows (messages/saved_lessons), each with a
    handful of citations, on fast local disk with no Qdrant optimizer to wait on. A one-time UPDATE
    here is seconds, not days — that reasoning does not transfer to this table.

WHAT THIS DOES
    1. Reads every messages.citations / saved_lessons.citations row that isn't empty.
    2. Collects the distinct refs where a citation's license AND version_title are BOTH still empty
       (never touches a citation that already has data, even if it looks incomplete).
    3. Looks those refs up in the live `chavruta_commercial` collection in batches (ref carries a
       keyword payload index, so this is fast, unlike an unindexed field scan).
    4. Rewrites just those two fields on the affected citation dicts and writes the JSON back.
    5. A ref genuinely absent from the corpus (or still without rights data) is left exactly as it
       was — never guessed.

USAGE
    python scripts/backfill_message_citation_rights.py --dry-run   # measure + report, write nothing
    python scripts/backfill_message_citation_rights.py             # do it
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app.db as db  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402
from qdrant_client.http import models  # noqa: E402

COLLECTION = "chavruta_commercial"
QDRANT = os.environ.get("CHAVRUTA_QDRANT_URL", "http://localhost:6333")


def _resolve_refs(client: QdrantClient, refs: list[str]) -> dict[str, tuple[str, str]]:
    """ref -> (license, version_title) for every ref found in the corpus with rights data."""
    out: dict[str, tuple[str, str]] = {}
    batch_size = 200
    for i in range(0, len(refs), batch_size):
        batch = refs[i:i + batch_size]
        points, _ = client.scroll(
            COLLECTION,
            scroll_filter=models.Filter(must=[models.FieldCondition(
                key="ref", match=models.MatchAny(any=batch))]),
            limit=len(batch) * 3,   # a ref can repeat across chunks sharing the same base title
            with_payload=["ref", "license", "version_title"],
        )
        for p in points:
            ref = p.payload.get("ref")
            lic = p.payload.get("license") or ""
            ver = p.payload.get("version_title") or ""
            if ref and ref not in out and (lic or ver):
                out[ref] = (lic, ver)
    return out


def _rows(table: str) -> list:
    conn = db.get_conn()
    return conn.execute(
        f"SELECT rowid, citations FROM {table} "  # noqa: S608 — table name is one of two literals below
        "WHERE citations IS NOT NULL AND citations != '' AND citations != '[]'"
    ).fetchall()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="measure and report; write nothing")
    args = ap.parse_args()

    client = QdrantClient(url=QDRANT, timeout=60)

    targets: list[tuple[str, int, list[dict]]] = []
    missing_refs: set[str] = set()
    for table in ("messages", "saved_lessons"):
        for row in _rows(table):
            cits = json.loads(row["citations"])
            needs = [c for c in cits if not (c.get("license") or "").strip()
                     and not (c.get("version_title") or "").strip()]
            if needs:
                targets.append((table, row["rowid"], cits))
                missing_refs.update(c["ref"] for c in needs if c.get("ref"))

    print(f"① {len(targets)} rows across messages/saved_lessons have citations missing rights "
          f"({len(missing_refs)} distinct refs)", flush=True)

    resolved = _resolve_refs(client, sorted(missing_refs))
    print(f"② resolved {len(resolved):,}/{len(missing_refs):,} refs from the live corpus", flush=True)

    updated_rows = 0
    updated_citations = 0
    still_missing: set[str] = set()
    for table, rowid, cits in targets:
        changed = False
        for c in cits:
            if (c.get("license") or "").strip() or (c.get("version_title") or "").strip():
                continue
            ref = c.get("ref")
            hit = resolved.get(ref)
            if hit:
                c["license"], c["version_title"] = hit
                changed = True
                updated_citations += 1
            elif ref:
                still_missing.add(ref)
        if changed:
            updated_rows += 1
            if not args.dry_run:
                with db._tx(db.get_conn()) as conn:
                    conn.execute(f"UPDATE {table} SET citations=? WHERE rowid=?",  # noqa: S608
                                (json.dumps(cits, ensure_ascii=False), rowid))

    print(f"\n{'[DRY RUN] would update' if args.dry_run else 'updated'} {updated_rows} row(s), "
          f"{updated_citations} citation(s).")
    if still_missing:
        print(f"unresolved: {len(still_missing)} ref(s) — left untouched, not guessed. "
              f"sample: {sorted(still_missing)[:10]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
