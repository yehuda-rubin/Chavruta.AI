#!/usr/bin/env python3
"""Build a flat English→Hebrew title map from Sefaria's table of contents.

The script walks Sefaria's API index tree and extracts every work's English title
and Hebrew title (heTitle). The output is a JSON map suitable for Hebrew display
of corpus refs.

Usage:
    python scripts/build_hebrew_titles.py
"""

from __future__ import annotations

import json
from pathlib import Path

import requests


def _get_json(endpoint: str) -> dict | list:
    """Fetch a Sefaria API endpoint, matching the pattern in fetch_licensed_local.py."""
    url = f"https://www.sefaria.org/api/{endpoint}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def build_hebrew_titles() -> dict[str, dict[str, str]]:
    """Walk the Sefaria TOC and return {English title: {"he": Hebrew title, "cat": top category}}.

    The top-level category travels with each title because the consumer must treat Talmud
    differently from everything else: the corpus stores Bavli refs amud-linearly, so a Talmud ref's
    numbers need the daf/amud conversion in refs.py and must NOT be rendered straight through. The
    category is what lets `hebrew_display_ref` refuse the generic path for exactly those titles
    instead of confidently printing a wrong daf (see refs.py, `_split_book`).
    """
    toc = _get_json("index/")
    titles: dict[str, dict[str, str]] = {}

    def walk(node, top_cat: str):
        """Recursively walk the TOC tree, extracting titles from leaf nodes."""
        if "contents" in node:
            # This is a category — recurse into its children
            for child in node["contents"]:
                walk(child, top_cat)
        else:
            # This is a leaf node — extract title and heTitle
            title = node.get("title")
            he_title = node.get("heTitle")
            if title and he_title:
                titles[title] = {"he": he_title, "cat": top_cat}

    for node in toc:
        walk(node, node.get("category", "") or "")

    return titles


def main() -> None:
    """Fetch, build, and write the Hebrew titles map."""
    print("Fetching Sefaria table of contents...")
    titles = build_hebrew_titles()
    print(f"Found {len(titles)} titles with Hebrew translations")

    # Package data (ships with the code), NOT the repo's gitignored `data/` directory — a table
    # written there would work locally and be missing in the deployed image.
    output_path = (Path(__file__).parent.parent / "src" / "chavruta" / "corpus" / "data"
                   / "hebrew_titles.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(titles, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")  # trailing newline

    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
