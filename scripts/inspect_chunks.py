"""בדיקת מבנה all_chunks.json"""
import json

data = json.load(open("data/processed/all_chunks.json", encoding="utf-8"))
chunks = data["chunks"]
print(f"Total chunks: {len(chunks)}")

print("\n=== Chunk[0] (Chumash) ===")
c = chunks[0]
print("  id:", c["id"])
print("  document:", repr(c["document"][:100]))
print("  metadata keys:", list(c["metadata"].keys()))
for k, v in c["metadata"].items():
    print(f"    {k}: {repr(str(v)[:60])}")

rashi = next((c for c in chunks if c["metadata"].get("chunk_type")=="rashi"), None)
if rashi:
    print("\n=== First Rashi chunk ===")
    print("  id:", rashi["id"])
    print("  document:", repr(rashi["document"][:100]))
    for k, v in rashi["metadata"].items():
        print(f"    {k}: {repr(str(v)[:60])}")
