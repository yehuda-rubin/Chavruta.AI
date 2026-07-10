# -*- coding: utf-8 -*-
"""build_links_job.py — ENRICH the link graph with Sefaria cross-references (Nebius CPU job).

The corpus-derived graph (scripts/build_corpus_links.py) already covers the commentary→base
backbone. This job adds what that can't: Sefaria's NON-commentary cross-references — quotations,
parallels, 'reference' links (a pasuk cited in the Gemara, parallel sugyot, Midrash↔Tanakh, …).

Pipeline (all in one job):
  1. Load the corpus canonical-ref set from ref_index.db (built by build_link_index.py; if running
     on a fresh Nebius box, first download ref_index.db from HF chavruta-index-links).
  2. For each distinct BASE ref in the corpus, fetch Sefaria /links/ (concurrent, rate-limited,
     resumable), keep edges where category != 'Commentary' AND BOTH endpoints resolve in the corpus
     (via canonical_ref) — so every added edge is usable.
  3. Merge with data/links_corpus.jsonl (commentary edges) → final links_corpus.jsonl + links_corpus.db.
  4. Upload everything to HF (scripts/upload_links_hf.py) so the linker ships with the RAG.

This is pure I/O (no GPU, no LLM) → a cheap Nebius CPU job. ALWAYS dry-run a small sample first:

    # local sanity check on 200 refs (no upload):
    .venv/Scripts/python.exe scripts/build_links_job.py --sample 200
    # full run on Nebius (CPU job), then publish:
    python scripts/build_links_job.py --workers 16 --upload --hf-token $HF_TOKEN

Nebius submission (sketch — no GPU needed):
    nebius compute ... run a CPU container that does:
      pip install requests huggingface_hub qdrant-client
      python scripts/build_links_job.py --workers 16 --upload --hf-token $HF_TOKEN
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from chavruta.corpus.refs import canonical_ref

DATA = REPO / "data"
REF_DB = DATA / "ref_index.db"
COMMENTARY = DATA / "links_corpus.jsonl"
OUT_JSONL = DATA / "links_corpus.jsonl"        # merged output (commentary + cross-refs)
OUT_DB = DATA / "links_corpus.db"
RESUME = DATA / "sefaria_links.raw.jsonl"      # raw fetched edges (resume checkpoint)
API = "https://www.sefaria.org/api/links"


def load_corpus(ref_db: Path) -> tuple[set[str], list[str]]:
    """Return (canonical ref set, distinct base ORIGINAL refs to fetch links for)."""
    con = sqlite3.connect(f"file:{ref_db}?mode=ro", uri=True)
    canon = {r[0] for r in con.execute("SELECT DISTINCT canon FROM refidx")}
    # base texts = rows that are NOT commentaries ('x on y'); fetch cross-refs for those
    bases = [r[0] for r in con.execute(
        "SELECT DISTINCT chunk_ref FROM refidx WHERE canon NOT LIKE '% on %'")]
    con.close()
    return canon, bases


def fetch_links(ref: str, session) -> list[dict]:
    """Fetch Sefaria links for one ref; return raw link dicts (best-effort, never raises)."""
    try:
        url = f"{API}/{ref.replace('_', ' ').replace(' ', '%20')}"
        r = session.get(url, timeout=20)
        if r.status_code != 200:
            return []
        return r.json() if isinstance(r.json(), list) else []
    except Exception:
        return []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=0, help="fetch only N base refs (dry run, no upload)")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--rate", type=float, default=0.05, help="seconds between requests per worker")
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--hf-token", default=None)
    args = ap.parse_args()

    if not REF_DB.exists():
        raise SystemExit(f"{REF_DB} missing — build it (scripts/build_link_index.py) or download from HF first")

    import requests
    canon, bases = load_corpus(REF_DB)
    if args.sample:
        bases = bases[: args.sample]
    print(f"corpus: {len(canon):,} canonical refs | fetching cross-refs for {len(bases):,} base refs")

    session = requests.Session()
    session.headers["User-Agent"] = "Chavruta.AI link-graph builder"

    kept = seen_raw = 0
    t0 = time.time()
    with RESUME.open("w", encoding="utf-8") as raw, ThreadPoolExecutor(max_workers=args.workers) as ex:
        def job(ref):
            time.sleep(args.rate)
            return ref, fetch_links(ref, session)

        for i, fut in enumerate(as_completed(ex.submit(job, b) for b in bases), 1):
            ref, links = fut.result()
            base_canon = canonical_ref(ref)
            for lk in links:
                if (lk.get("category") == "Commentary"):
                    continue                       # commentaries already covered by the corpus graph
                to = lk.get("ref") or lk.get("anchorRef")
                if not to:
                    continue
                to_canon = canonical_ref(to)
                seen_raw += 1
                if to_canon and to_canon != base_canon and to_canon in canon:  # usable edge only
                    raw.write(json.dumps({"from_ref": base_canon, "to_ref": to_canon,
                                          "link_type": lk.get("type", "reference"), "to_work_id": ""},
                                         ensure_ascii=False) + "\n")
                    kept += 1
            if i % 2000 == 0:
                print(f"  {i:,}/{len(bases):,} refs | kept {kept:,} cross-ref edges | {time.time()-t0:.0f}s", flush=True)

    print(f"\nfetched cross-ref edges: seen {seen_raw:,} → kept (both in corpus) {kept:,}")
    if args.sample:
        print("sample dry-run complete (no merge/upload). Inspect", RESUME)
        return

    # merge commentary edges + cross-ref edges → final graph (jsonl + on-disk db)
    print("merging commentary + cross-ref edges → final graph …")
    edges = set()
    for src in (COMMENTARY, RESUME):
        if src.exists():
            with src.open(encoding="utf-8") as f:
                for line in f:
                    d = json.loads(line)
                    edges.add((d["from_ref"], d["to_ref"], d.get("link_type", "commentary")))
    if OUT_DB.exists():
        OUT_DB.unlink()
    g = sqlite3.connect(OUT_DB)
    g.execute("PRAGMA journal_mode=OFF"); g.execute("PRAGMA synchronous=OFF")
    g.execute("CREATE TABLE edges (from_canon TEXT, to_canon TEXT)")
    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for a, b, t in edges:
            f.write(json.dumps({"from_ref": a, "to_ref": b, "link_type": t, "to_work_id": ""},
                               ensure_ascii=False) + "\n")
            g.execute("INSERT INTO edges VALUES (?,?)", (a, b))
            g.execute("INSERT INTO edges VALUES (?,?)", (b, a))
    g.commit(); g.execute("CREATE INDEX idx_from ON edges(from_canon)"); g.commit(); g.close()
    print(f"final graph: {len(edges):,} edges → {OUT_JSONL.name} + {OUT_DB.name}")

    if args.upload:
        import subprocess
        subprocess.run([sys.executable, str(REPO / "scripts" / "upload_links_hf.py"),
                        "--token", args.hf_token or ""], check=True)


if __name__ == "__main__":
    main()
