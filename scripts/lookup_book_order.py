"""Run ON the host: the load order (rowid) of each catalogue book's first chunk in data/search_index.db.

rowid is the canonical order the corpus was loaded in (Genesis -> Deuteronomy, Seder Zeraim -> Nezikin,
Bavli tractates in Seder order), which the alphabetical English titles of the catalogue lose. The library tree
and book search use it to order books inside one category. Read-only; one indexed range lookup per book (a `ref =` lookup is NOT indexed: 5,423 full scans).
Usage: python3 lookup_book_order.py < catalog.json > book_order.json   (from the repo root, inside the search container)
"""
import json, sqlite3, sys

books = json.load(sys.stdin)["books"]
c = sqlite3.connect("file:data/search_index.db?mode=ro", uri=True)
import re
out, missing = {}, 0
for b in books:
    m = re.match(r"^(.*) (\d+(?::\d+)*)$", b["first_ref"])
    if not m:
        missing += 1
        continue
    corpus_ref = m.group(1).replace(" ", "_") + "." + m.group(2).replace(":", ".")
    # chunk_id is '<corpus ref>_<work_id>' and UNIQUE-indexed: a range lookup, never a table scan
    row = c.execute("SELECT rowid FROM chunks WHERE chunk_id >= ? AND chunk_id < ? LIMIT 1", (corpus_ref + "_", corpus_ref + "`")).fetchone()
    if row is None:
        missing += 1
        continue
    out[b["title_en"]] = row[0]
print("missing", missing, file=sys.stderr)
json.dump(out, sys.stdout, ensure_ascii=False)
