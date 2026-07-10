# -*- coding: utf-8 -*-
"""build_links_job.py — ENRICH the link graph with Sefaria cross-references (resumable I/O job).

The corpus-derived graph (scripts/build_corpus_links.py) already covers the commentary→base
backbone. This job adds what that can't: Sefaria's NON-commentary cross-references — quotations,
parallels, 'reference' links (a pasuk cited in the Gemara, parallel sugyot, Midrash↔Tanakh, …).

RESUMABLE + RETRYING (survives a multi-hour unattended run):
  • Every base ref that is fetched successfully is checkpointed to data/sefaria_links.done.
  • Kept edges are APPENDED to data/sefaria_links.raw.jsonl (never truncated mid-run).
  • On restart the job loads .done and SKIPS finished refs — it only fetches what's left.
  • A fetch that errors/times-out/429s is retried (exponential backoff); if it still fails it is
    NOT marked done, so the NEXT run re-requests it. Re-run until "remaining: 0", then it merges.

Pipeline: fetch cross-refs → keep only edges whose BOTH endpoints resolve in the corpus (via
canonical_ref) → merge with data/links_corpus.jsonl → rebuild links_corpus.jsonl + links_corpus.db
→ (optional) upload to HF. Pure I/O, no GPU/LLM — runs locally or as a Nebius CPU job.

    # sanity check (200 refs, no merge/upload):
    .venv/Scripts/python.exe scripts/build_links_job.py --sample 200
    # full run — re-runnable; resumes automatically. Add --upload to publish when complete:
    .venv/Scripts/python.exe scripts/build_links_job.py --workers 8 --rate 0.1 --upload
    # start over from scratch:
    .venv/Scripts/python.exe scripts/build_links_job.py --fresh ...
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
OUT_JSONL = DATA / "links_corpus.jsonl"
OUT_DB = DATA / "links_corpus.db"
RAW = DATA / "sefaria_links.raw.jsonl"     # kept cross-ref edges (append-only)
DONE = DATA / "sefaria_links.done"         # base refs successfully fetched (checkpoint)
API = "https://www.sefaria.org/api/links"
RETRIES = 4


def load_corpus(ref_db: Path) -> tuple[set[str], list[str]]:
    con = sqlite3.connect(f"file:{ref_db}?mode=ro", uri=True)
    canon = {r[0] for r in con.execute("SELECT DISTINCT canon FROM refidx")}
    bases = [r[0] for r in con.execute(
        "SELECT DISTINCT chunk_ref FROM refidx WHERE canon NOT LIKE '% on %'")]
    con.close()
    return canon, bases


def fetch_links(ref: str, session) -> tuple[bool, list[dict]]:
    """(ok, links). ok=True means a definitive answer was obtained (mark done). ok=False means the
    request failed after retries — leave it UN-done so a later run retries it."""
    url = f"{API}/{ref.replace('_', ' ').replace(' ', '%20')}"
    for attempt in range(RETRIES):
        try:
            r = session.get(url, timeout=25)
            if r.status_code == 200:
                data = r.json()
                return True, (data if isinstance(data, list) else [])
            if r.status_code == 404:
                return True, []                       # no links for this ref — definitively done
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(min(30, 2 ** attempt))     # backoff on throttle / transient server error
                continue
            return True, []                           # other 4xx → nothing to fetch, done
        except Exception:
            time.sleep(min(15, 1 + 2 * attempt))
    return False, []                                  # exhausted retries → retry on next run


def enrich(canon: set[str], bases: list[str], workers: int, rate: float) -> tuple[int, int]:
    done: set[str] = set()
    if DONE.exists():
        with DONE.open(encoding="utf-8") as f:
            done = {ln.strip() for ln in f if ln.strip()}
    todo = [b for b in bases if b not in done]
    print(f"  base refs: {len(bases):,} total | already done: {len(done):,} | to fetch now: {len(todo):,}")
    if not todo:
        return 0, 0

    import requests
    session = requests.Session()
    session.headers["User-Agent"] = "Chavruta.AI link-graph builder (contact: project maintainer)"

    kept = failed = processed = 0
    t0 = time.time()
    with RAW.open("a", encoding="utf-8") as raw, DONE.open("a", encoding="utf-8") as donef, \
            ThreadPoolExecutor(max_workers=workers) as ex:
        def job(ref):
            time.sleep(rate)
            ok, links = fetch_links(ref, session)
            return ref, ok, links

        for ref, ok, links in (fut.result() for fut in as_completed(ex.submit(job, b) for b in todo)):
            processed += 1
            if not ok:
                failed += 1
                continue
            base_canon = canonical_ref(ref)
            for lk in links:
                if lk.get("category") == "Commentary":
                    continue                          # commentaries already in the corpus graph
                to = lk.get("ref") or lk.get("anchorRef")
                if not to:
                    continue
                tc = canonical_ref(to)
                if tc and tc != base_canon and tc in canon:   # usable edge only
                    raw.write(json.dumps({"from_ref": base_canon, "to_ref": tc,
                                          "link_type": lk.get("type", "reference"), "to_work_id": ""},
                                         ensure_ascii=False) + "\n")
                    kept += 1
            donef.write(ref + "\n")                    # checkpoint AFTER writing its edges
            if processed % 1000 == 0:
                raw.flush(); donef.flush()
                rate_now = processed / max(time.time() - t0, 1)
                eta = (len(todo) - processed) / max(rate_now, 0.1) / 3600
                print(f"    {processed:,}/{len(todo):,} | kept {kept:,} | failed {failed:,} | "
                      f"{rate_now:.0f} ref/s | ETA {eta:.1f}h", flush=True)
    return kept, failed


def merge_and_build() -> int:
    print("merging commentary + cross-ref edges → final graph …")
    edges = set()
    for src in (COMMENTARY, RAW):
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
    return len(edges)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=0, help="fetch only N refs (dry run, no merge/upload)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--rate", type=float, default=0.1, help="seconds between requests per worker (politeness)")
    ap.add_argument("--upload", action="store_true", help="publish to HF when the fetch is complete")
    ap.add_argument("--hf-token", default=None)
    ap.add_argument("--fresh", action="store_true", help="discard prior checkpoint and start over")
    args = ap.parse_args()

    if not REF_DB.exists():
        raise SystemExit(f"{REF_DB} missing — build it (scripts/build_link_index.py) or download from HF first")
    if args.fresh:
        for p in (RAW, DONE):
            p.unlink(missing_ok=True)
        print("fresh start — cleared checkpoints")

    canon, bases = load_corpus(REF_DB)
    if args.sample:
        bases = bases[: args.sample]
    print(f"corpus: {len(canon):,} canonical refs")

    kept, failed = enrich(canon, bases, args.workers, args.rate)
    total_done = len({ln.strip() for ln in DONE.open(encoding='utf-8')} if DONE.exists() else set())
    remaining = len(bases) - total_done
    print(f"\nthis run: kept {kept:,} edges | failed (will retry) {failed:,}")
    print(f"progress: {total_done:,}/{len(bases):,} base refs done | remaining: {remaining:,}")

    if args.sample:
        print("sample dry-run — inspect", RAW)
        return
    if remaining > 0:
        print(f"⚠ {remaining:,} refs still to fetch — RE-RUN the same command to resume (it skips done refs).")
        return

    merge_and_build()
    if args.upload:
        import subprocess
        subprocess.run([sys.executable, str(REPO / "scripts" / "upload_links_hf.py")]
                       + (["--token", args.hf_token] if args.hf_token else []), check=True)
    else:
        print("done fetching. Run scripts/upload_links_hf.py to publish to HF.")


if __name__ == "__main__":
    main()
