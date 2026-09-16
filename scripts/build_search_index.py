"""build_search_index.py — Build SQLite FTS5 search index from HuggingFace dataset JSONL files.

Usage:
    python scripts/build_search_index.py                       # All 15 tiers
    python scripts/build_search_index.py --only tanakh         # Single tier
    python scripts/build_search_index.py --local-dir data/hf   # Local directory of <tier>.jsonl files
    python scripts/build_search_index.py --jsonl-file sample.jsonl --output data/search_index.db

Produces an SQLite database (data/search_index.db by default) with:
  - Table `chunks`: All chunk metadata, full vocalized text_he, and text_en.
  - Virtual table `search_fts`: FTS5 index over `search_he` and `search_en`
    pointing to `chunks` as an external content table.
  - B-tree indexes for fast canonical ordering and facet counts.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Iterable

# Add project root to sys.path so chavruta package imports work
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chavruta.corpus.normalize import deuphemize_he, normalize_he

CANONICAL_ORDER: dict[str, int] = {
    "tanakh": 0,
    "mishnah": 1,
    "tosefta": 2,
    "gemara": 3,
    "yerushalmi": 4,
    "midrash": 5,
    "halacha": 6,
    "shut": 7,
    "kabbalah": 8,
    "chasidut": 9,
    "jewish_thought": 10,
    "musar": 11,
    "liturgy": 12,
    "second_temple": 13,
    "reference": 14,
}

ALL_TIERS: list[str] = [
    "tanakh",
    "mishnah",
    "tosefta",
    "gemara",
    "yerushalmi",
    "midrash",
    "halacha",
    "shut",
    "kabbalah",
    "chasidut",
    "jewish_thought",
    "musar",
    "liturgy",
    "second_temple",
    "reference",
]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS chunks (
    rowid         INTEGER PRIMARY KEY,
    chunk_id      TEXT UNIQUE NOT NULL,
    ref           TEXT NOT NULL,
    book          TEXT NOT NULL,
    author_he     TEXT,
    work_id       TEXT NOT NULL,
    period        TEXT,
    search_he     TEXT,
    search_en     TEXT,
    text_he       TEXT,
    text_en       TEXT,
    license_he    TEXT,
    license_en    TEXT,
    version_he    TEXT,
    version_en    TEXT,
    category_path TEXT,
    canon_order   INTEGER NOT NULL,
    sort_title    TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
    search_he,
    search_en,
    content='chunks',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);
"""

INDEX_AND_TRIGGERS_SQL = """
CREATE INDEX IF NOT EXISTS idx_work ON chunks(work_id);
CREATE INDEX IF NOT EXISTS idx_canon ON chunks(canon_order, sort_title);

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO search_fts(rowid, search_he, search_en) VALUES (new.rowid, new.search_he, new.search_en);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO search_fts(search_fts, rowid, search_he, search_en) VALUES('delete', old.rowid, old.search_he, old.search_en);
END;
CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO search_fts(search_fts, rowid, search_he, search_en) VALUES('delete', old.rowid, old.search_he, old.search_en);
    INSERT INTO search_fts(rowid, search_he, search_en) VALUES (new.rowid, new.search_he, new.search_en);
END;
"""


def init_database(conn: sqlite3.Connection) -> None:
    """Initialize chunks table and search_fts virtual table."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def finalize_database(conn: sqlite3.Connection) -> None:
    """Rebuild FTS5 index and create secondary indexes + triggers."""
    print("Rebuilding FTS5 index...")
    conn.execute("INSERT INTO search_fts(search_fts) VALUES('rebuild');")
    conn.commit()

    print("Creating B-tree indexes and triggers...")
    conn.executescript(INDEX_AND_TRIGGERS_SQL)
    conn.commit()

    print("Optimizing SQLite database...")
    conn.execute("PRAGMA optimize;")
    conn.commit()


def parse_chunk_record(raw: dict[str, Any], default_work_id: str = "") -> dict[str, Any]:
    """Extract and normalize all fields from a JSON chunk object."""
    meta = raw.get("metadata") or {}

    chunk_id = str(raw.get("chunk_id") or raw.get("id") or meta.get("chunk_id") or meta.get("verse_id") or "")
    ref = str(raw.get("ref") or meta.get("ref") or "")
    book = str(raw.get("book") or meta.get("book") or "")
    author_he = str(raw.get("author_he") or meta.get("author_he") or "")
    work_id = str(raw.get("work_id") or raw.get("work") or meta.get("work_id") or meta.get("work") or default_work_id or "")
    period = str(raw.get("period") or meta.get("period") or "")

    text_he = raw.get("text_he") or meta.get("text_he") or ""
    text_en = raw.get("text_en") or meta.get("text_en") or ""

    license_he = raw.get("license_he") or meta.get("license_he") or ""
    license_en = raw.get("license_en") or meta.get("license_en") or ""
    version_he = raw.get("version_he") or meta.get("version_he") or ""
    version_en = raw.get("version_en") or meta.get("version_en") or ""
    category_path = raw.get("category_path") or meta.get("category_path") or ""

    canon_order = CANONICAL_ORDER.get(work_id.lower(), 99)
    sort_title = normalize_he(author_he or book or ref or "")

    search_he = normalize_he(deuphemize_he(text_he)) if text_he else ""
    search_en = text_en.lower().strip() if text_en else ""

    return {
        "chunk_id": chunk_id,
        "ref": ref,
        "book": book,
        "author_he": author_he,
        "work_id": work_id,
        "period": period,
        "search_he": search_he,
        "search_en": search_en,
        "text_he": text_he,
        "text_en": text_en,
        "license_he": license_he,
        "license_en": license_en,
        "version_he": version_he,
        "version_en": version_en,
        "category_path": category_path,
        "canon_order": canon_order,
        "sort_title": sort_title,
    }


def insert_batch(conn: sqlite3.Connection, batch: list[dict[str, Any]]) -> None:
    """Insert a batch of parsed records into the chunks table."""
    if not batch:
        return
    sql = """
    INSERT OR REPLACE INTO chunks (
        chunk_id, ref, book, author_he, work_id, period,
        search_he, search_en, text_he, text_en,
        license_he, license_en, version_he, version_en,
        category_path, canon_order, sort_title
    ) VALUES (
        :chunk_id, :ref, :book, :author_he, :work_id, :period,
        :search_he, :search_en, :text_he, :text_en,
        :license_he, :license_en, :version_he, :version_en,
        :category_path, :canon_order, :sort_title
    )
    """
    conn.executemany(sql, batch)
    conn.commit()


def process_jsonl_stream(
    lines: Iterable[str],
    conn: sqlite3.Connection,
    default_work_id: str = "",
    batch_size: int = 50000,
) -> int:
    """Parse JSONL lines and insert in batches. Returns count of inserted records."""
    batch: list[dict[str, Any]] = []
    total = 0
    for line in lines:
        line = line.strip().lstrip("\ufeff")
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        record = parse_chunk_record(data, default_work_id=default_work_id)
        if not record["chunk_id"]:
            continue
        batch.append(record)

        if len(batch) >= batch_size:
            insert_batch(conn, batch)
            total += len(batch)
            batch = []

    if batch:
        insert_batch(conn, batch)
        total += len(batch)

    return total


def build_from_file(
    jsonl_path: Path,
    conn: sqlite3.Connection,
    work_id: str = "",
    batch_size: int = 50000,
) -> int:
    """Process a single JSONL file into the database."""
    slug = work_id or jsonl_path.stem.replace(".manifest", "")
    with jsonl_path.open("r", encoding="utf-8") as f:
        count = process_jsonl_stream(f, conn, default_work_id=slug, batch_size=batch_size)
    print(f"  + {jsonl_path.name}: {count:,} records")
    return count


def build_index(
    output_path: Path | str,
    *,
    tiers: list[str] | None = None,
    jsonl_file: Path | str | None = None,
    local_dir: Path | str | None = None,
    batch_size: int = 50000,
    hf_namespace: str = "Yehuda-Rubin",
    hf_token: str | None = None,
) -> int:
    """Main build function to create the search index."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if out.exists():
        out.unlink()

    conn = sqlite3.connect(str(out))
    conn.execute("PRAGMA synchronous = OFF;")
    conn.execute("PRAGMA journal_mode = MEMORY;")
    conn.execute("PRAGMA cache_size = -64000;")  # ~64MB cache

    init_database(conn)
    total_records = 0
    t0 = time.time()

    if jsonl_file:
        p = Path(jsonl_file)
        if not p.exists():
            raise FileNotFoundError(f"JSONL file not found: {p}")
        total_records += build_from_file(p, conn, batch_size=batch_size)
    elif local_dir:
        ld = Path(local_dir)
        if not ld.exists():
            raise FileNotFoundError(f"Local directory not found: {ld}")
        target_tiers = tiers or ALL_TIERS
        for slug in target_tiers:
            candidates = [ld / f"{slug}.jsonl", ld / f"{slug}_chunks.jsonl"]
            found = False
            for cand in candidates:
                if cand.exists():
                    total_records += build_from_file(cand, conn, work_id=slug, batch_size=batch_size)
                    found = True
                    break
            if not found:
                print(f"  ! Warning: {slug}.jsonl not found in {ld}")
    else:
        # Download from HuggingFace
        from huggingface_hub import hf_hub_download

        token = hf_token or os.environ.get("HF_TOKEN")
        target_tiers = tiers or ALL_TIERS
        for slug in target_tiers:
            repo = f"{hf_namespace}/chavruta-commercial-{slug}"
            print(f"Fetching {repo} ({slug}.jsonl)...")
            try:
                local_file = hf_hub_download(
                    repo_id=repo,
                    filename=f"{slug}.jsonl",
                    repo_type="dataset",
                    token=token,
                )
                total_records += build_from_file(Path(local_file), conn, work_id=slug, batch_size=batch_size)
            except Exception as e:
                print(f"  ! Error downloading {slug} from HF: {e}")

    finalize_database(conn)
    conn.close()

    elapsed = time.time() - t0
    print(f"\nDone! Indexed {total_records:,} chunks into {out} in {elapsed:.1f}s")
    return total_records


def main() -> None:
    parser = argparse.ArgumentParser(description="Build SQLite FTS5 search index for Chavruta.AI")
    parser.add_argument("--output", default="data/search_index.db", help="Path to output SQLite database")
    parser.add_argument("--only", default=None, help="Process only a single tier (e.g. tanakh)")
    parser.add_argument("--local-dir", default=None, help="Directory containing pre-downloaded <tier>.jsonl files")
    parser.add_argument("--jsonl-file", default=None, help="Single JSONL file to index directly")
    parser.add_argument("--batch-size", type=int, default=50000, help="Batch size for SQLite transactions")
    parser.add_argument("--hf-namespace", default="Yehuda-Rubin", help="Hugging Face namespace for tiers")
    parser.add_argument("--hf-token", default=None, help="Hugging Face API token")

    args = parser.parse_args()

    tiers = [args.only] if args.only else None

    build_index(
        output_path=args.output,
        tiers=tiers,
        jsonl_file=args.jsonl_file,
        local_dir=args.local_dir,
        batch_size=args.batch_size,
        hf_namespace=args.hf_namespace,
        hf_token=args.hf_token,
    )


if __name__ == "__main__":
    main()
