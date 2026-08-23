#!/usr/bin/env python3
"""backfill_commercial_rights.py — correct per-chunk `license`/`version_title` on the LIVE
`chavruta_commercial` collection, sourced from the tier manifests that already record exactly
which edition was fetched — NOT from a live re-query to Sefaria's current default.

WHY NOT scripts/backfill_licenses.py FOR THIS COLLECTION
    That script asks Sefaria's API for each title's DEFAULT (highest-`priority`) edition today, and
    writes that back. That is sound for a fetch that took Sefaria's default and never recorded
    which edition it got. The commercial fetch is the OPPOSITE of that: `docs/COMMERCIAL_CORPUS.md`
    exists entirely because the default is often CC-BY-NC ("שליפה בלי version= מקבלת את ברירת
    המחדל של ספריא... הפתרון הוא לבקש מהדורה מפורשת") — the commercial notebooks deliberately
    requested a DIFFERENT, explicit `version=` per source. Running backfill_licenses.py against
    `chavruta_commercial` would tag many titles — the Talmud tractates especially — with whatever
    Sefaria now serves by DEFAULT (the CC-BY-NC Davidson edition), not the CC-BY-SA Wikisource
    edition actually sitting in the collection. Verified live 2026-08-21: Sefaria's own
    `/api/texts/versions/Yoma` still lists Davidson ahead of Wikisource by priority. That is not a
    missing-data problem — it would be a WRONG-data one, actively mislabelling CC-BY-SA text as
    something else.

WHAT THIS DOES INSTEAD
    Every `chavruta-commercial-<tier>` HF dataset already ships a `licenses.json` recording, per
    source title, EXACTLY the (license, versionTitle) that was fetched — because the fetch notebook
    chose it deliberately (least legally-encumbered commercial edition) and wrote it down at fetch
    time. Verified live 2026-08-21 across all 15 tiers: 5,828 distinct resolvable titles, ZERO
    cross-tier licence collisions. This script:
      1. downloads and merges all 15 tiers' `licenses.json` into one title -> (license, version) map
      2. scans the live collection once, REUSING `backfill_licenses.py`'s `scan_corpus` /
         `index_title_of` / `apply_to_qdrant` — already proven, already addresses points BY ID
         (not an unindexed `ref` filter — see that script's own "12 days" note)
      3. for every distinct title found, looks up the CORRECT rights from the merged manifest
      4. writes `license` + `version_title` (not split by language — prefers he_license/he_version,
         falls back to en_license/en_version, mirroring the same fix already applied in
         `corpus/ingest.py::payload_from_legacy_meta`)
      5. never guesses: a title absent from every manifest is reported unresolved and left untouched

SCOPE
    Only fixes `license`/`version_title` on Sefaria-sourced content already in the live collection.
    Wikisource-sourced tiers (`chavruta-wikisource-*`) carry correct license/version/deep_link at
    fetch time already (fixed 2026-08-21) — loading them through the now-fixed
    `payload_from_legacy_meta` needs no backfill at all. `deep_link` on existing Sefaria-sourced
    points is untouched here because it was never wrong for them (`sefaria.org/{ref}` IS correct
    when `ref` really is a Sefaria ref).

USAGE
    python scripts/backfill_commercial_rights.py --dry-run          # measure + report, write nothing
    python scripts/backfill_commercial_rights.py                    # do it
    python scripts/backfill_commercial_rights.py --titles 50        # bounded trial run first

⚠️ NOT RUN against a live collection from this session — no Qdrant was reachable. `--dry-run` first.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

# Reuse, don't reimplement, the already-proven scan/write machinery — only the rights LOOKUP
# changes (manifest instead of live Sefaria query).
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "chavruta_backfill_licenses", ROOT / "scripts" / "backfill_licenses.py"
)
_bl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bl)  # defines functions only; argparse/network calls live in main()

scan_corpus = _bl.scan_corpus
apply_to_qdrant = _bl.apply_to_qdrant
COLLECTION = _bl.COLLECTION

NAMESPACE = "Yehuda-Rubin"
ALL_TIERS = ["second_temple", "reference", "musar", "tosefta", "liturgy", "kabbalah", "midrash",
             "chasidut", "jewish_thought", "shut", "yerushalmi", "mishnah", "tanakh", "halacha", "gemara"]


def build_manifest(tiers: list[str]) -> tuple[dict[str, tuple[str, str]], list[tuple]]:
    """title -> (license, version_title), merged across every tier's licenses.json.

    Prefers the Hebrew edition's rights (the corpus is Hebrew-first — Principle IV, and matches
    the same he-over-en preference already applied in ingest.py). Collisions (same title, different
    licence, across two tiers) are reported, not silently resolved — that would be guessing.
    """
    import urllib.request

    manifest: dict[str, tuple[str, str]] = {}
    collisions: list[tuple] = []
    for tier in tiers:
        url = f"https://huggingface.co/datasets/{NAMESPACE}/chavruta-commercial-{tier}/resolve/main/licenses.json"
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                d = json.load(r)
        except Exception as exc:
            print(f"  ! {tier}: failed to fetch licenses.json ({exc}) — skipped", flush=True)
            continue
        n = 0
        for s in d.get("sources", []):
            if s.get("status") != "kept":
                continue
            title = s.get("title") or ""
            lic = s.get("he_license") or s.get("en_license") or ""
            ver = s.get("he_version") or s.get("en_version") or ""
            if not title or not lic:
                continue
            if title in manifest and manifest[title][0] != lic:
                collisions.append((title, manifest[title], (lic, ver, tier)))
                continue  # keep the first-seen entry; don't silently overwrite a disagreement
            manifest[title] = (lic, ver)
            n += 1
        print(f"  + {tier:16} {n:>5,} titles", flush=True)
    return manifest, collisions


def resolve_rights(title: str, manifest: dict[str, tuple[str, str]]) -> tuple[str, str] | None:
    """Look up `title`, falling back to progressively shorter comma-prefixes.

    Found live (2026-08-23) against the real merged manifest: a multi-volume/sectioned work's
    licenses.json entry is inconsistently granular — some are recorded per volume already
    ('Mishneh Torah, Positive Mitzvot'), but most are recorded only at the top work level
    ('Arukh HaShulchan', 'Beit Yosef', 'Torah Temimah on Torah') while the LIVE collection's
    per-chunk title correctly keeps Sefaria's own sub-index ('Arukh HaShulchan, Yoreh De'ah',
    'Torah Temimah on Torah, Leviticus') — every volume of one physical sefer shares its parent's
    licence and edition by construction, so this is not a guess: it is matching what the manifest
    itself already asserts (one licence per base work, regardless of which volume recorded it) to
    a chunk whose title happens to carry the fuller name. Strips ONE trailing ", segment" at a
    time (not straight to the first comma) so an already volume-qualified manifest entry like
    'Shem HaGedolim, Maarekhet Sefarim' still matches a chunk titled '..., Part 2' without losing
    the qualifier it already has.
    """
    t = title
    while True:
        if t in manifest:
            return manifest[t]
        if "," not in t:
            return None
        t = t.rsplit(",", 1)[0].strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="measure and report; write nothing")
    ap.add_argument("--titles", type=int, default=0, help="only process the N biggest titles by chunk count")
    ap.add_argument("--tiers", default=",".join(ALL_TIERS), help="comma list to override the tier set")
    args = ap.parse_args()

    tiers = [t.strip() for t in args.tiers.split(",") if t.strip()]

    print("① merging tier manifests (licenses.json — the edition ACTUALLY fetched)…", flush=True)
    manifest, collisions = build_manifest(tiers)
    print(f"   {len(manifest):,} resolvable titles, {len(collisions):,} cross-tier collisions\n", flush=True)
    if collisions:
        print("   collisions (kept the first-seen entry, did NOT guess):", flush=True)
        for title, first, second in collisions[:20]:
            print(f"     {title!r}: {first} vs {second}", flush=True)
        print(flush=True)

    print("② scanning the live collection (one pass: titles + their point ids)…", flush=True)
    titles, ids_by_title = scan_corpus()
    ordered = titles.most_common(args.titles or None)
    total_chunks = sum(c for _, c in ordered)
    print(f"   {len(ordered):,} distinct titles over {total_chunks:,} chunks\n", flush=True)

    resolved_chunks = unresolved_chunks = 0
    unresolved_titles: list[str] = []
    t0 = time.time()
    for i, (title, n_chunks) in enumerate(ordered, 1):
        rights = resolve_rights(title, manifest)
        if not rights:
            unresolved_chunks += n_chunks
            unresolved_titles.append(title)
            continue
        license_str, version_title = rights
        resolved_chunks += n_chunks
        if not args.dry_run:
            apply_to_qdrant(ids_by_title[title], {"license": license_str, "version_title": version_title})
        if i % 200 == 0:
            print(f"   {i:,}/{len(ordered):,} titles ({time.time() - t0:.0f}s)", flush=True)

    print(f"\n{'[DRY RUN] would have written' if args.dry_run else 'wrote'} rights onto "
          f"{resolved_chunks:,} chunks across {len(ordered) - len(unresolved_titles):,} titles.")
    print(f"unresolved: {len(unresolved_titles):,} titles, {unresolved_chunks:,} chunks "
          f"(no manifest entry — left untouched, not guessed).")
    if unresolved_titles:
        sample = unresolved_titles[:15]
        print("   sample unresolved titles:", ", ".join(repr(t) for t in sample))
    return 0


if __name__ == "__main__":
    sys.exit(main())
