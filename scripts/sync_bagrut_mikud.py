"""sync_bagrut_mikud.py — Dynamic, Zero-Deploy Bagrut Curriculum Sync.

Syncs active Ministry of Education Bagrut curriculum (tractates, chapters, exact page ranges,
and key topics) directly into SQLite (`bagrut_curriculum_cache` in /app-data/chavruta.db).

Because /app-data is a mounted volume:
- Updates take effect IMMEDIATELY in the running FastAPI application.
- ZERO Docker rebuilds, ZERO container restarts, ZERO redeployment.
- Can be run manually or as a monthly cron job.

Usage:
    python scripts/sync_bagrut_mikud.py             # Sync current curriculum to DB
    python scripts/sync_bagrut_mikud.py --check-only # Check without modifying
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

import yaml
from app.db import (
    get_conn,
    init_db,
    upsert_bagrut_curriculum_cache,
    list_active_bagrut_curricula_from_db,
)


def load_curriculum_specs() -> dict:
    curr_path = REPO_ROOT / "data" / "bagrut_curriculum.yaml"
    if not curr_path.exists():
        print(f"Error: {curr_path} not found")
        sys.exit(1)
    with open(curr_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("active_curriculum", {})


def sync_to_db(check_only: bool = False) -> None:
    init_db()
    active_specs = load_curriculum_specs()
    year_he = active_specs.get("version_year", "תשפ\"ו–תשפ\"ז")

    print(f"=== Chavruta.AI Bagrut Curriculum Sync ({year_he}) ===")
    if check_only:
        print("[Mode: Check Only]")

    items_to_sync = []
    for subject, exam_dict in active_specs.items():
        if not isinstance(exam_dict, dict) or subject == "version_year":
            continue
        for code, details in exam_dict.items():
            if not isinstance(details, dict):
                continue
            items_to_sync.append((subject, str(code), details))

    print(f"Found {len(items_to_sync)} active curriculum specifications to verify/sync.\n")

    for subj, code, det in items_to_sync:
        tractate = det.get("tractate") or det.get("mishnah_tractate") or det.get("tractate_book") or ""
        ref_prefix = det.get("ref_prefix", "")
        chapter = det.get("chapter") or (det.get("mishnah_chapters", [""])[0] if isinstance(det.get("mishnah_chapters"), list) else det.get("chapter", ""))
        daf_range = det.get("daf_range") or det.get("daf_verses_he") or ""
        pages = det.get("pages") or []
        topics = det.get("key_topics") or []
        queries = det.get("canonical_queries") or []
        track = det.get("track", "mmd")
        units = det.get("units", 5)

        print(f"► [{subj.upper()}] Code {code} ({det.get('name_he', '')})")
        print(f"   Tractate: {tractate} | Chapter: {chapter}")
        print(f"   Pages: {daf_range} (pages count: {len(pages)})")
        print(f"   Topics: {len(topics)} topics, {len(queries)} canonical search queries")

        if not check_only:
            upsert_bagrut_curriculum_cache(
                subject=subj,
                track=track,
                units=units,
                exam_code=code,
                year_he=year_he,
                tractate_book=tractate,
                ref_prefix=ref_prefix,
                chapter_he=chapter,
                daf_verses_he=daf_range,
                page_range=pages,
                key_topics=topics,
                canonical_queries=queries,
                source_url="https://meyda.education.gov.il",
                is_active=1,
            )
            print("   -> Synced to SQLite cache [OK]")
        print()

    active_in_db = list_active_bagrut_curricula_from_db()
    print(f"✅ Total active specifications in database: {len(active_in_db)}")


def main():
    parser = argparse.ArgumentParser(description="Sync Bagrut Curriculum to SQLite")
    parser.add_argument("--check-only", action="store_true", help="Verify without writing to DB")
    args = parser.parse_args()
    sync_to_db(check_only=args.check_only)


if __name__ == "__main__":
    main()
