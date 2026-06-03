"""בדיקה מהירה של התיקון — פרק א בראשית בלבד."""
import sys
sys.path.insert(0, ".")

from pathlib import Path
from scripts.fetch_sefaria import SefariaClient, join_commentary_verse, CACHE_DIR

CACHE_DIR.mkdir(parents=True, exist_ok=True)
client = SefariaClient(cache_dir=CACHE_DIR)

print("בודק רש\"י ברמת פסוק על בראשית א:1-6...\n")
for v in range(1, 7):
    data = client.fetch_verse_commentary("Rashi on", "Bereishit", 1, v) or {}
    en   = join_commentary_verse(data.get("text"))
    he   = join_commentary_verse(data.get("he"))
    has  = bool(en or he)
    print(f"  א:{v}  has_rashi={has}  en={en[:60]!r}")

print("\nבודק רמב\"ן על בראשית א:1-6...\n")
for v in range(1, 7):
    data = client.fetch_verse_commentary("Ramban on", "Bereishit", 1, v) or {}
    en   = join_commentary_verse(data.get("text"))
    has  = bool(en or join_commentary_verse(data.get("he")))
    print(f"  א:{v}  has_ramban={has}  en={en[:60]!r}")
