#!/usr/bin/env python3
"""Backfill per-chunk rights onto an ALREADY-INDEXED collection — without re-embedding.

WHY THIS EXISTS
    The corpus was ingested with a fetch that read `text` out of Sefaria's response and dropped the
    `license` / `versionTitle` fields sitting right beside it, and the registry then labelled every
    work "CC0 / Sefaria". That is false. Verified live 2026-07-17: Talmud Bavli's default edition
    (William Davidson) is CC-BY-NC in Hebrew AND English; `Steinsaltz on Mishneh Torah` is
    "Copyright: Steinsaltz Center" with no Creative Commons grant at all. Both were being cited by
    the running system while labelled CC0.

WHY IT DOESN'T RE-EMBED
    A licence is metadata, not meaning: it is a property of (title, language, versionTitle), and
    changing it does not change a single vector. So this walks the DISTINCT titles in the collection,
    asks Sefaria what each one's editions actually are, and writes the answer onto the existing
    points with set_payload. No GPU, no re-download, no re-index. Vectors are never touched.

USAGE
    python scripts/backfill_licenses.py --dry-run          # measure + report, write nothing
    python scripts/backfill_licenses.py                    # do it
    python scripts/backfill_licenses.py --titles 50        # bounded trial run first

Resumable: progress is journalled per title, so an interrupted run picks up where it stopped.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chavruta.corpus.rights import allows_commercial_use, is_unknown  # noqa: E402

SEFARIA = "https://www.sefaria.org"
QDRANT = "http://localhost:6333"
COLLECTION = "chavruta"
STATE = ROOT / "data" / "license_backfill.json"     # {title: {"license_he":..., ...}} — the journal


# ── plumbing ─────────────────────────────────────────────────────────────────

def _qdrant(path: str, body: dict | None = None, method: str = "POST") -> dict:
    req = urllib.request.Request(
        f"{QDRANT}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def _sefaria_versions(title: str) -> list[dict]:
    """All editions Sefaria holds for a title, with their licences. [] if the title is unknown."""
    url = f"{SEFARIA}/api/texts/versions/{urllib.parse.quote(title)}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                data = json.load(r)
                return data if isinstance(data, list) else []
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []                       # not a real index title (e.g. our ref-splitting)
            time.sleep(2 * (attempt + 1))
        except Exception:
            time.sleep(2 * (attempt + 1))
    return []


# A stored ref carries a Hebrew display label the ingest prepended: 'רש"י on Rashi on Chullin 11.3.1'.
# Sefaria's index title is the part AFTER it ('Rashi on Chullin'); the prefix is ours, not theirs.
_HE_LABEL_PREFIX = re.compile(r"^[^A-Za-z]*?\s+on\s+(?=[A-Za-z])")
# Two locator shapes exist in the corpus, and only handling one is why an early version of this
# script produced ~113k "titles" from 200k chunks — every dotted ref became its own title:
#   space form : 'Rashi on Chullin 11.3.1'   'Berakhot 2a.3'
#   dotted form: "Prisha,_Yoreh_De'ah.335.19.1"   'Mishneh_Torah,_Forbidden_Foods.11.18'
_LOCATOR_SPACE = re.compile(r"\s+\d+[ab]?([.:]\d+)*$")
_LOCATOR_DOTTED = re.compile(r"\.\d+[ab]?([.:]\d+)*$")


def index_title_of(ref: str) -> str:
    """Best-effort Sefaria index title from a stored ref.

    A heuristic by necessity — the ingest did not record which title it fetched. A title we get
    wrong simply 404s at Sefaria and is counted as unresolved; it is never labelled by guesswork.
    """
    ref = (ref or "").strip()
    if not ref:
        return ""
    ref = _HE_LABEL_PREFIX.sub("", ref)          # drop our own Hebrew display prefix
    prev = None
    while prev != ref:                            # peel the locator, whichever shape it took
        prev = ref
        ref = _LOCATOR_SPACE.sub("", ref)
        ref = _LOCATOR_DOTTED.sub("", ref)
    return ref.replace("_", " ").strip(" .,")     # the dotted form URL-encodes spaces


def distinct_titles() -> Counter:
    """Walk every point's ref (payload only — no vectors) and count chunks per index title."""
    titles: Counter = Counter()
    nxt, seen = None, 0
    while True:
        body = {"limit": 5000, "with_payload": ["ref"], "with_vector": False}
        if nxt:
            body["offset"] = nxt
        res = _qdrant(f"/collections/{COLLECTION}/points/scroll", body)["result"]
        for p in res["points"]:
            t = index_title_of((p.get("payload") or {}).get("ref") or "")
            if t:
                titles[t] += 1
            seen += 1
        nxt = res.get("next_page_offset")
        print(f"\r  scanned {seen:,} chunks → {len(titles):,} distinct titles", end="", flush=True)
        if not nxt:
            break
    print()
    return titles


def rights_for(title: str) -> dict:
    """The licence of the DEFAULT edition per language — i.e. what the ingest actually pulled.

    Sefaria serves the highest-priority version when none is named, which is what the original
    unversioned fetch received. Mirror that choice so the backfill describes the text we hold.
    """
    out = {"license_he": "", "version_he": "", "license_en": "", "version_en": ""}
    versions = _sefaria_versions(title)
    if not versions:
        return out
    for lang, lic_key, ver_key in (("he", "license_he", "version_he"),
                                   ("en", "license_en", "version_en")):
        cands = [v for v in versions if (v.get("language") or "").lower().startswith(lang)]
        if not cands:
            continue
        # Sefaria's own ordering puts the default first; priority breaks ties when present.
        best = max(cands, key=lambda v: (v.get("priority") or 0))
        out[lic_key] = best.get("license") or ""
        out[ver_key] = best.get("versionTitle") or ""
    return out


def apply_to_qdrant(title: str, rights: dict) -> None:
    """Stamp the rights onto every chunk of this title. Vectors untouched — payload only."""
    _qdrant(f"/collections/{COLLECTION}/points/payload?wait=true", {
        "payload": rights,
        "filter": {"must": [{"key": "ref", "match": {"text": title}}]},
    })


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="measure and report; write nothing")
    ap.add_argument("--titles", type=int, default=0, help="only process the N biggest titles")
    ap.add_argument("--sleep", type=float, default=0.2, help="pause between Sefaria calls")
    args = ap.parse_args()

    print("① counting distinct titles in the live collection…", flush=True)
    titles = distinct_titles()
    ordered = titles.most_common(args.titles or None)
    total_chunks = sum(titles.values())
    print(f"   {len(titles):,} titles over {total_chunks:,} chunks")
    print(f"   ~{len(ordered):,} Sefaria calls ≈ {len(ordered) * args.sleep / 60:.0f} min\n")

    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    lic_counts: Counter = Counter()
    chunks_by_verdict: Counter = Counter()
    unresolved = 0

    print("② asking Sefaria for each title's real licence…", flush=True)
    for i, (title, n_chunks) in enumerate(ordered, 1):
        if title in state:
            r = state[title]
        else:
            r = rights_for(title)
            state[title] = r
            time.sleep(args.sleep)
            if i % 50 == 0:
                STATE.parent.mkdir(parents=True, exist_ok=True)
                STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

        lic = r.get("license_he") or r.get("license_en")
        if not any(r.values()):
            unresolved += 1
        lic_counts[lic or "(unresolved)"] += 1
        verdict = "commercial-OK" if allows_commercial_use(lic) else (
            "UNKNOWN" if is_unknown(lic) else "RESTRICTED")
        chunks_by_verdict[verdict] += n_chunks

        if not args.dry_run and any(r.values()):
            apply_to_qdrant(title, r)
        print(f"\r  {i:,}/{len(ordered):,}  {title[:44]:44} {str(lic)[:22]:22}", end="", flush=True)

    print()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    print("\n③ what the corpus actually is\n")
    print(f"   {'licence':32} titles")
    for lic, n in lic_counts.most_common(18):
        flag = "  ok " if allows_commercial_use(lic) else ("  ?? " if lic == "(unresolved)" else " STOP")
        print(f"  {flag} {str(lic)[:32]:32} {n:,}")
    print(f"\n   unresolved titles: {unresolved:,}  (heuristic title-from-ref missed; not mislabelled)")
    print("\n   CHUNKS by commercial verdict:")
    for verdict, n in chunks_by_verdict.most_common():
        pct = 100.0 * n / total_chunks if total_chunks else 0
        print(f"     {verdict:14} {n:>10,}  ({pct:5.1f}%)")
    if args.dry_run:
        print("\n   DRY RUN — nothing was written.")
    else:
        print(f"\n   payload updated on {total_chunks:,} chunks. Vectors untouched.")
        print("   next: python scripts/create_payload_indexes.py   (index `license_he`/`license_en`)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
