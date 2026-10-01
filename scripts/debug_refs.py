import sqlite3

db = sqlite3.connect('data/search_index.db')
db.row_factory = sqlite3.Row

clean_ref = "Iggeret Shmuel on Ruth 3:1:1"
print(f"--- QUERYING COMMENTARIES IN SEARCH INDEX FOR: {clean_ref} ---")

# Extract base verse (e.g. Ruth 3:1 from Iggeret Shmuel on Ruth 3:1:1)
# Ref structure: [Author] on [Book] [Chapter]:[Verse]:[Segment]
import re
m = re.search(r"on\s+(.*?)\s+(\d+:\d+)", clean_ref, re.IGNORECASE)
if m:
    book_part = m.group(1) # Ruth
    ch_vs = m.group(2)    # 3:1
    print(f"Base book: '{book_part}', Verse: '{ch_vs}'")

    # Search for all commentaries on this verse
    sql = "SELECT ref, book, author_he, category_path, text_he FROM chunks WHERE ref LIKE ? OR ref LIKE ? OR ref = ? LIMIT 20"
    p1 = f"%on {book_part} {ch_vs}:%"
    p2 = f"%on {book_part}.{ch_vs.replace(':', '.')}.%"
    p3 = f"{book_part} {ch_vs}"
    rows = db.execute(sql, (p1, p2, p3)).fetchall()
    print(f"FOUND {len(rows)} COMMENTARIES/PARALLELS:")
    for r in rows:
        print("  -", r["author_he"], "|", r["ref"])
