"""compare_corpus.py — Cross-reference Otzaria & Wikisource against existing Chavruta corpus.
Filters out books already present in Chavruta and checks blacklist / categories.
"""

from __future__ import annotations

import json
import re
import urllib.request
from collections import Counter
from pathlib import Path

CHAVRUTA_TITLES_FILE = Path("src/chavruta/corpus/data/hebrew_titles.json")
OTZARIA_MANIFEST_URL = "https://raw.githubusercontent.com/Sivan22/otzaria-library/main/files_manifest.json"
OTZARIA_BLACKLIST_URL = "https://raw.githubusercontent.com/Sivan22/otzaria-library/main/books%20lists/%D7%90%D7%95%D7%A6%D7%A8%D7%99%D7%90/blackList.txt"


def normalize_title(title: str) -> str:
    """Aggressively normalizes book titles for robust cross-corpus deduplication."""
    if not title:
        return ""
    # Strip .txt / .json
    t = re.sub(r"\.(?:txt|json|csv|xlsx)$", "", title, flags=re.IGNORECASE)
    # Strip nikkud
    t = re.sub(r"[\u0591-\u05C7]", "", t)
    # Strip quotes, gershayim, geresh, punctuation, dashes
    t = re.sub(r"[\'\"״״׳\-\–—\(\)\[\]\.,]", "", t)
    # Strip generic prefixes
    t = re.sub(r"^(ספר|קונטרס|פירוש|ביאור|על|מסכת)\s+", "", t.strip())
    # Collapse spaces
    t = re.sub(r"\s+", " ", t).strip()
    return t.lower()


def load_chavruta_titles() -> set[str]:
    """Loads and normalizes all titles currently indexed in Chavruta."""
    if not CHAVRUTA_TITLES_FILE.exists():
        print(f"Warning: {CHAVRUTA_TITLES_FILE} not found.")
        return set()

    with open(CHAVRUTA_TITLES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    seen = set()
    for en_title, info in data.items():
        if en_title:
            seen.add(normalize_title(en_title))
        he_title = info.get("he", "")
        if he_title:
            seen.add(normalize_title(he_title))
            # Also add without author prefix if present e.g. "רש\"י על בראשית" -> "בראשית"
            if " על " in he_title:
                seen.add(normalize_title(he_title.split(" על ", 1)[1]))
    return seen


def load_otzaria_blacklist() -> set[str]:
    """Fetches the official Otzaria community blacklist (secular, academic, non-Orthodox)."""
    try:
        req = urllib.request.Request(OTZARIA_BLACKLIST_URL, headers={"User-Agent": "ChavrutaBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            lines = resp.read().decode("utf-8", errors="ignore").splitlines()
            return {normalize_title(line) for line in lines if line.strip() and not line.startswith("#")}
    except Exception as e:
        print(f"Could not load Otzaria blacklist: {e}")
        return set()


def analyze_otzaria():
    print("=== Analyzing Otzaria Corpus vs Chavruta ===")
    chavruta_titles = load_chavruta_titles()
    blacklist = load_otzaria_blacklist()
    print(f"Loaded {len(chavruta_titles)} normalized titles from Chavruta.")
    print(f"Loaded {len(blacklist)} blacklisted titles from Otzaria.")

    print(f"Fetching Otzaria manifest from {OTZARIA_MANIFEST_URL}...")
    req = urllib.request.Request(OTZARIA_MANIFEST_URL, headers={"User-Agent": "ChavrutaBot/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        manifest = json.loads(resp.read().decode("utf-8"))

    total_books = len(manifest)
    print(f"Total books listed in Otzaria manifest: {total_books}")

    already_in_chavruta = []
    blacklisted = []
    new_approved_books = []

    for path in manifest.keys():
        parts = path.split("/")
        if len(parts) > 1 and parts[0] == "אוצריא":
            cat = parts[1]
            filename = parts[-1]
            book_name = filename[:-4] if filename.endswith(".txt") else filename
            norm_name = normalize_title(book_name)

            if norm_name in blacklist:
                blacklisted.append((cat, book_name))
            elif norm_name in chavruta_titles:
                already_in_chavruta.append((cat, book_name))
            else:
                new_approved_books.append((cat, book_name, path))

    print(f"\n[Deduplication Results]")
    print(f"- Books already in Chavruta (Filtered OUT): {len(already_in_chavruta)}")
    print(f"- Books on Blacklist (Filtered OUT): {len(blacklisted)}")
    print(f"- NEW, KOSHER & APPROVED Books to ingest: {len(new_approved_books)}")

    cat_counts = Counter(cat for cat, _, _ in new_approved_books)
    print("\n[Breakdown of NEW books by Otzaria category]:")
    for cat, count in cat_counts.most_common():
        print(f"  * {cat}: {count} new books")

    # Sample of new books
    print("\n[Sample of 10 New Books Chavruta does not have yet]:")
    for cat, name, _ in new_approved_books[:10]:
        print(f"  [{cat}] {name}")

    # Save new books list to JSON for future ingestion
    out_file = Path("data/new_books_from_otzaria.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump([{"category": c, "title": t, "path": p} for c, t, p in new_approved_books], f, ensure_ascii=False, indent=2)
    print(f"\nSaved list of {len(new_approved_books)} new candidate books to {out_file}")


if __name__ == "__main__":
    analyze_otzaria()
