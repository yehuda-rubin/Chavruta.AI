"""Run ON the host: for each corpus first_ref (stdin JSON list) find the reader's own ref for that
chunk in data/search_index.db, so a library link opens in the reader that serves it.

The reader indexes display refs ('Genesis 1:1'); the corpus uses 'Genesis.1.1'. chunk_id is
'<corpus ref>_<work_id>' and is UNIQUE-indexed, so this is one range lookup per book (no table scan
of the 5.9 GB file). Read-only.
    ssh -i ~/.ssh/chavruta_nebius chavruta@<host> 'cd ~/chavruta && nice -n 10 python3 - ' < ... 
Usage: python3 lookup_reader_refs.py < first_refs.json > reader_refs.json   (run from the repo root)
"""
import json, sqlite3, sys

refs = json.load(sys.stdin)
c = sqlite3.connect("file:data/search_index.db?mode=ro", uri=True)
out = {}
for r in refs:
    row = c.execute(
        "SELECT ref, book, author_he, work_id, category_path FROM chunks "
        "WHERE chunk_id >= ? AND chunk_id < ? LIMIT 1", (r + "_", r + "`")).fetchone()
    if row:
        out[r] = {"ref": row[0], "book": row[1], "author_he": row[2], "work_id": row[3], "category_path": row[4]}
json.dump(out, sys.stdout, ensure_ascii=False)
