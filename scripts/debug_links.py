import sqlite3
import os

links_db_path = "data/links.db"
if not os.path.exists(links_db_path):
    links_db_path = "/data/links.db"

if os.path.exists(links_db_path):
    db = sqlite3.connect(links_db_path)
    db.row_factory = sqlite3.Row
    print("--- LINKS DB EDGES TEST ---")
    rows1 = db.execute("SELECT from_canon, to_canon, link_type FROM edges WHERE from_canon LIKE '%Ruth%' LIMIT 20").fetchall()
    print("FROM RUTH:")
    for r in rows1:
        print(" ", dict(r))

    rows2 = db.execute("SELECT from_canon, to_canon, link_type FROM edges WHERE to_canon LIKE '%Iggeret%Shmuel%' LIMIT 20").fetchall()
    print("\nTO IGGERET SHMUEL:")
    for r in rows2:
        print(" ", dict(r))
