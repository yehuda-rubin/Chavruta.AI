"""
בדיקה מקיפה של Vector DB — Chavruta.AI
בודק: רלוונטיות, כיסוי, עברית, דיוק מקורות, edge cases
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).parent.parent
CHROMA_DB_PATH = ROOT / "data" / "chroma_db"
EMBEDDING_MODEL = "BAAI/bge-m3"   # רב-לשוני (עברית+אנגלית), 1024 מימד
COLLECTION_NAME = "chavruta_torah"

print("טוען מודל ו-DB...")
model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
model.max_seq_length = 512   # תואם לבנייה
client = chromadb.PersistentClient(
    path=str(CHROMA_DB_PATH),
    settings=Settings(anonymized_telemetry=False),
)
col = client.get_collection(COLLECTION_NAME)
print(f"DB נטען. סה\"כ וקטורים: {col.count():,}\n")


def query(text, n=5, filter_type=None):
    """שאילתה עם embedding ישיר (לא query_texts של Chroma)."""
    vec = model.encode([text], normalize_embeddings=True).tolist()
    kwargs = dict(query_embeddings=vec, n_results=n,
                  include=["metadatas", "distances", "documents"])
    if filter_type:
        kwargs["where"] = {"chunk_type": filter_type}
    r = col.query(**kwargs)
    return list(zip(r["metadatas"][0], r["distances"][0], r["documents"][0]))


def show(results, label=""):
    if label:
        print(f"  ── {label}")
    for meta, dist, doc in results:
        book  = meta.get("book","?")
        ch    = meta.get("chapter","?")
        vs    = meta.get("verse","?")
        ct    = meta.get("chunk_type","?").upper()
        cmt   = meta.get("commentator","")
        tag   = f"{ct}/{cmt}" if cmt else ct
        score = 1 - dist   # cosine similarity (גבוה = טוב יותר)
        # שורה ראשונה של ה-document
        first_line = doc.split("\n")[0]
        print(f"    [{tag}] {book} {ch}:{vs}  sim={score:.3f}  | {first_line}")
    print()


SEP = "═" * 65

# ════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("  1. שאילתות נושאיות — אנגלית")
print(SEP)

tests = [
    ("Shabbat and rest on the seventh day",     "בריאה/שבת"),
    ("Noah and the flood",                       "נוח"),
    ("Tower of Babel confusion of languages",    "מגדל בבל"),
    ("binding of Isaac Akeda sacrifice",         "עקידת יצחק"),
    ("Jacob and Esau birthright",                "עשו ויעקב"),
    ("Joseph sold by his brothers Egypt",        "יוסף במצרים"),
    ("snake serpent Garden of Eden sin",         "גן עדן"),
    ("circumcision covenant Abraham",            "ברית מילה"),
]
for q, label in tests:
    results = query(q, n=3)
    print(f"\n🔍 \"{q}\"")
    show(results, label)

# ════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("  2. שאילתות בעברית")
print(SEP)

heb_tests = [
    ("בראשית ברא אלהים",          "פסוק ראשון"),
    ("ויהי ערב ויהי בוקר",         "ששת ימי בריאה"),
    ("לך לך מארצך",                "ציווי לאברהם"),
    ("ויחלם והנה סלם מוצב ארצה",   "חלום יעקב"),
    ("רש\"י מסביר את הפסוק הראשון", "רש\"י על בראשית א"),
]
for q, label in heb_tests:
    results = query(q, n=3)
    print(f"\n🔍 \"{q}\"")
    show(results, label)

# ════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("  3. סינון לפי סוג — רש\"י בלבד vs רמב\"ן בלבד")
print(SEP)

topic = "creation light darkness first day"
print(f"\n🔍 \"{topic}\"")
print("  → רש\"י בלבד:")
show(query(topic, n=3, filter_type="rashi"))
print("  → רמב\"ן בלבד:")
show(query(topic, n=3, filter_type="ramban"))
print("  → חומש בלבד:")
show(query(topic, n=3, filter_type="chumash"))

# ════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("  4. בדיקת דיוק — שאילתות עם תשובה ידועה")
print(SEP)

known = [
    ("In the beginning God created the heavens and the earth", "Bereishit", 1, 1),
    ("And God said let there be light", "Bereishit", 1, 3),
    ("God rested on the seventh day", "Bereishit", 2, 2),
    ("Cain killed Abel his brother", "Bereishit", 4, 8),
    ("Abraham was ninety nine years old circumcision", "Bereishit", 17, 1),
]

hits = 0
for q, exp_book, exp_ch, exp_vs in known:
    results = query(q, n=1)
    meta, dist, _ = results[0]
    got_book = meta.get("book","")
    got_ch   = int(meta.get("chapter", 0))
    got_vs   = int(meta.get("verse", 0))
    correct  = (got_book == exp_book and got_ch == exp_ch and got_vs == exp_vs)
    hits += correct
    icon = "✅" if correct else "❌"
    sim  = 1 - dist
    print(f"  {icon} \"{q[:50]}\"")
    print(f"     ציפיתי: {exp_book} {exp_ch}:{exp_vs} | קיבלתי: {got_book} {got_ch}:{got_vs}  sim={sim:.3f}")
print(f"\n  דיוק Top-1: {hits}/{len(known)} ({100*hits/len(known):.0f}%)\n")

# ════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("  5. Edge cases — שאילתות קשות")
print(SEP)

edge = [
    "What does Rashi say about this verse",
    "מה ההבדל בין רש\"י לרמב\"ן",
    "hello world",
    "אברהם אבינו",
    "Why did God create the world",
]
for q in edge:
    results = query(q, n=2)
    print(f"\n🔍 \"{q}\"")
    show(results)

print(f"{SEP}")
print("  סיום בדיקה")
print(SEP)
