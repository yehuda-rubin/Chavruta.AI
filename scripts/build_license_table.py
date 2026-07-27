"""Download and merge the per-tier licenses.json files from Hugging Face.

The commercial corpus was built by selecting one commercially-licensed edition per work
and recording which one in a per-tier licenses.json. This script downloads all 16 tiers,
merges the kept sources into one table, and writes it to the repo.

This is the authoritative record of what was actually ingested — asking Sefaria today
would tell you which editions exist, not which one is in our index.

Tiers: tanakh mishnah gemara yerushalmi tosefta midrash halacha shut musar jewish_thought
kabbalah chasidut liturgy reference second_temple (skip the -index repos — those are vectors).
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from collections import defaultdict

# The 16 tiers that have licenses.json files
TIERS = [
    "tanakh", "mishnah", "gemara", "yerushalmi", "tosefta", "midrash", "halacha", "shut",
    "musar", "jewish_thought", "kabbalah", "chasidut", "liturgy", "reference", "second_temple"
]

HF_BASE_URL = "https://huggingface.co/datasets/Yehuda-Rubin/chavruta-commercial-{tier}/resolve/main/licenses.json"

# Output path in the repo (beside the existing intents/data/ pattern)
OUTPUT_DIR = Path("src/chavruta/corpus/data")
OUTPUT_FILE = OUTPUT_DIR / "licenses.json"


def download_tier(tier: str) -> dict:
    """Download licenses.json for a single tier from Hugging Face."""
    url = HF_BASE_URL.format(tier=tier)
    print(f"Downloading {tier} from {url}")
    try:
        # A timeout is not optional here. Without one this call blocks forever on a stalled
        # connection, and the whole script simply hangs with no output — observed for 68 minutes.
        # The agent header is belt-and-braces: some CDNs in front of these hosts answer the default
        # "Python-urllib/3.x" with 403.
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8.5.0"})
        with urllib.request.urlopen(req, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data
    except Exception as e:
        print(f"  ERROR: failed to download {tier}: {e}")
        return {}


def merge_licenses(tier_data: list[dict]) -> dict:
    """Merge the per-tier license data into one table keyed by Sefaria title.

    Keeps: he_license, he_version, en_license, en_version.
    Drops: chunks, status, period (to keep the table small for per-hit reads).

    Reports any titles that appear in multiple tiers with conflicting licences.
    """
    merged: dict[str, dict] = {}
    conflicts: list[tuple[str, dict, dict]] = []

    for tier_dict in tier_data:
        tier_name = tier_dict.get("tier", "unknown")
        sources = tier_dict.get("sources", [])
        for source in sources:
            title = source.get("title")
            if not title:
                continue
            # Only sources actually INGESTED. A "skipped" row is a work that had no commercially
            # usable edition and was deliberately left out of the corpus — precisely the
            # non-commercial material. Attributing one would credit a text we do not serve.
            if source.get("status") != "kept":
                continue

            entry = {
                "he_license": source.get("he_license", ""),
                "he_version": source.get("he_version", ""),
                "en_license": source.get("en_license", ""),
                "en_version": source.get("en_version", ""),
            }

            if title in merged:
                # Check for conflicts
                existing = merged[title]
                if (entry["he_license"] != existing["he_license"] or
                    entry["en_license"] != existing["en_license"]):
                    conflicts.append((title, existing, entry))
                    # Keep the first one encountered (arbitrary but deterministic)
            else:
                merged[title] = entry

    return merged, conflicts


def main():
    """Download all tiers, merge, and write the table."""
    print(f"Building license table from {len(TIERS)} tiers...")

    # Download all tiers
    tier_data = []
    for tier in TIERS:
        data = download_tier(tier)
        if data:
            tier_data.append(data)

    if not tier_data:
        print("ERROR: no tier data downloaded")
        return

    # Merge
    print("\nMerging license data...")
    merged, conflicts = merge_licenses(tier_data)

    # Print summary
    print(f"\nSummary:")
    print(f"  Total titles in table: {len(merged)}")

    # Count licence mix
    he_licence_counts = defaultdict(int)
    en_licence_counts = defaultdict(int)
    for entry in merged.values():
        he_licence_counts[entry["he_license"]] += 1
        en_licence_counts[entry["en_license"]] += 1

    print(f"\nHebrew licence distribution:")
    for lic, count in sorted(he_licence_counts.items(), key=lambda x: -x[1]):
        print(f"  {lic}: {count}")

    print(f"\nEnglish licence distribution:")
    for lic, count in sorted(en_licence_counts.items(), key=lambda x: -x[1]):
        print(f"  {lic}: {count}")

    # Report conflicts
    if conflicts:
        print(f"\n⚠️  Found {len(conflicts)} titles with conflicting licences across tiers:")
        for title, existing, new in conflicts[:10]:  # Show first 10
            print(f"  {title}:")
            print(f"    existing: he={existing['he_license']}, en={existing['en_license']}")
            print(f"    new:      he={new['he_license']}, en={new['en_license']}")
        if len(conflicts) > 10:
            print(f"  ... and {len(conflicts) - 10} more")
    else:
        print("\n✓ No licence conflicts found across tiers")

    # Write output
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    print(f"\nWrote license table to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
