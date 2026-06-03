"""
scripts/build_vectordb.py — Chavruta.AI
========================================
מטמיע את כל הצ'אנקים מ-data/processed/all_chunks.json
ושומר ב-ChromaDB מקומי (data/chroma_db/).

פורמט קלט (מ-process_chunks.py):
  {
    "metadata": {...},
    "chunks": [
      {
        "id": "Bereishit.1.1_chumash_0",
        "document": "[Chumash] Bereishit 1:1\n<עברית>\n<אנגלית>",
        "metadata": {
          "verse_id", "book", "book_he", "book_en", "book_num",
          "chapter", "verse", "chunk_type", "chunk_index",
          "total_chunks_for_type", "source_url", "has_rashi",
          "has_ramban", "text_en", "text_he", "char_count",
          "approx_tokens",
          # רש"י/רמב"ן בלבד:
          "commentator", "commentary_text_en", "commentary_text_he"
        }
      }, ...
    ]
  }

תכונות:
  • Batch embedding עם bge-small-en-v1.5 (CPU-optimized)
  • Resume: מדלג על IDs שכבר קיימים ב-DB
  • tqdm progress bars
  • דוח סופי עם נתוני אינדקס

פקודות:
  python scripts/build_vectordb.py                  # הטמעה מלאה
  python scripts/build_vectordb.py --reset          # מחיקת DB וחידוש מאפס
  python scripts/build_vectordb.py --verify         # בדיקת DB קיים + שאילתת ניסיון
"""

import sys
import json
import argparse
import logging
from pathlib import Path

from tqdm import tqdm

# ─── נתיבים ──────────────────────────────────────────────────────────────────
ROOT_DIR       = Path(__file__).resolve().parent.parent
DATA_PROCESSED = ROOT_DIR / "data" / "processed"
CHROMA_DB_PATH = ROOT_DIR / "data" / "chroma_db"

# ─── הגדרות ──────────────────────────────────────────────────────────────────
EMBEDDING_MODEL  = "BAAI/bge-m3"   # רב-לשוני (עברית+אנגלית), 1024 מימד
EMBEDDING_BATCH  = 8           # bge-m3 כבד פי ~17 — batch קטן ל-16GB RAM + CPU
EMBEDDING_MAX_SEQ = 512        # חיתוך אורך — חוסך זמן/RAM משמעותית ב-CPU
COLLECTION_NAME  = "chavruta_torah"
CHUNKS_FILE      = DATA_PROCESSED / "all_chunks.json"

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(ROOT_DIR / "build_vectordb.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════════
# ChromaDB helpers
# ════════════════════════════════════════════════════════════════════════════════

def get_collection(reset: bool = False):
    """מחזיר (או יוצר) את ה-collection ב-ChromaDB."""
    import chromadb
    from chromadb.config import Settings

    CHROMA_DB_PATH.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(
        path=str(CHROMA_DB_PATH),
        settings=Settings(anonymized_telemetry=False, allow_reset=True),
    )

    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
            log.info("Collection '%s' נמחק.", COLLECTION_NAME)
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={
            "hnsw:space":           "cosine",
            "hnsw:construction_ef": 100,
            "hnsw:M":               16,
        },
    )
    return collection


def get_existing_ids(collection) -> set:
    """מחזיר את כל ה-IDs הקיימים ב-collection (לצורך resume)."""
    try:
        result = collection.get(include=[])          # IDs בלבד, מהיר
        return set(result["ids"])
    except Exception:
        return set()


# ════════════════════════════════════════════════════════════════════════════════
# Embedding
# ════════════════════════════════════════════════════════════════════════════════

def load_model():
    """טוען את מודל ה-embedding עם אופטימיזציה ל-CPU."""
    from sentence_transformers import SentenceTransformer
    log.info("טוען מודל: %s ...", EMBEDDING_MODEL)
    model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
    model.max_seq_length = EMBEDDING_MAX_SEQ   # bge-m3 default=8192 — מקצר ל-CPU
    log.info("מודל נטען. מימד: %d", model.get_sentence_embedding_dimension())
    return model


def embed_batch(model, texts: list) -> list:
    """מטמיע batch של טקסטים, מחזיר רשימת וקטורים."""
    vectors = model.encode(
        texts,
        batch_size=EMBEDDING_BATCH,
        show_progress_bar=False,
        normalize_embeddings=True,   # נדרש ל-cosine similarity
        convert_to_numpy=True,
    )
    return vectors.tolist()


# ════════════════════════════════════════════════════════════════════════════════
# עיבוד מטא-נתונים
# ════════════════════════════════════════════════════════════════════════════════

def sanitize_metadata(raw_meta: dict) -> dict:
    """
    ממיר את מטא-נתוני הצ'אנק לפורמט ChromaDB-תואם.
    ChromaDB מקבל: str, int, float, bool בלבד.
    """
    def to_int(v, default=0):
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    def to_bool(v):
        if isinstance(v, bool):
            return v
        return str(v).lower() in ("true", "1", "yes")

    meta = {
        # שדות בסיסיים
        "verse_id":             str(raw_meta.get("verse_id", "")),
        "book":                 str(raw_meta.get("book", "")),
        "book_he":              str(raw_meta.get("book_he", "")),
        "book_en":              str(raw_meta.get("book_en", "")),
        "book_num":             to_int(raw_meta.get("book_num", 0)),
        "chapter":              to_int(raw_meta.get("chapter", 0)),
        "verse":                to_int(raw_meta.get("verse", 0)),

        # סוג צ'אנק
        "chunk_type":           str(raw_meta.get("chunk_type", "")),
        "chunk_index":          to_int(raw_meta.get("chunk_index", 0)),
        "total_chunks":         to_int(raw_meta.get("total_chunks_for_type", 1)),

        # קשרים
        "has_rashi":            to_bool(raw_meta.get("has_rashi", False)),
        "has_ramban":           to_bool(raw_meta.get("has_ramban", False)),

        # טקסט לתצוגה (מקוצר ל-ChromaDB)
        "text_he":              str(raw_meta.get("text_he", ""))[:500],
        "text_en":              str(raw_meta.get("text_en", ""))[:300],

        # מקור
        "source_url":           str(raw_meta.get("source_url", "")),

        # סטטיסטיקות
        "char_count":           to_int(raw_meta.get("char_count", 0)),
        "approx_tokens":        to_int(raw_meta.get("approx_tokens", 0)),
    }

    # שדות ייחודיים לפירושים
    commentator = raw_meta.get("commentator", "")
    if commentator:
        meta["commentator"] = str(commentator)
        meta["commentary_en"] = str(raw_meta.get("commentary_text_en", ""))[:400]
        meta["commentary_he"] = str(raw_meta.get("commentary_text_he", ""))[:400]
    else:
        meta["commentator"] = ""
        meta["commentary_en"] = ""
        meta["commentary_he"] = ""

    return meta


# ════════════════════════════════════════════════════════════════════════════════
# בניית DB
# ════════════════════════════════════════════════════════════════════════════════

def build(reset: bool = False) -> None:
    # ── טעינת צ'אנקים ────────────────────────────────────────────────────────
    if not CHUNKS_FILE.exists():
        log.error("קובץ צ'אנקים לא נמצא: %s", CHUNKS_FILE)
        log.error("הרץ תחילה: python scripts/process_chunks.py")
        sys.exit(1)

    log.info("טוען צ'אנקים מ-%s ...", CHUNKS_FILE)
    raw = json.loads(CHUNKS_FILE.read_text(encoding="utf-8"))

    # תמיכה בשני פורמטים: list ישיר או {"chunks": [...]}
    if isinstance(raw, dict):
        chunks = raw.get("chunks", [])
        file_meta = raw.get("metadata", {})
        log.info("מטא-נתוני קובץ: %s", file_meta)
    else:
        chunks = raw

    log.info("סה\"כ צ'אנקים: %d", len(chunks))

    # ── ChromaDB ──────────────────────────────────────────────────────────────
    collection   = get_collection(reset=reset)
    existing_ids = get_existing_ids(collection)

    if existing_ids:
        log.info("נמצאו %d צ'אנקים קיימים ב-DB — ממשיך מנקודת עצירה.", len(existing_ids))

    # סינון צ'אנקים חדשים בלבד
    new_chunks = [c for c in chunks if c["id"] not in existing_ids]
    log.info("צ'אנקים להוספה: %d", len(new_chunks))

    if not new_chunks:
        log.info("הכל כבר מוטמע. אין מה להוסיף.")
        return

    # ── מודל הטמעה ────────────────────────────────────────────────────────────
    model = load_model()

    # ── הטמעה ב-batches ───────────────────────────────────────────────────────
    total_batches = (len(new_chunks) + EMBEDDING_BATCH - 1) // EMBEDDING_BATCH

    pbar = tqdm(
        range(0, len(new_chunks), EMBEDDING_BATCH),
        total=total_batches,
        desc="🔢 מטמיע",
        unit="batch",
        colour="blue",
    )

    added = 0
    for start in pbar:
        batch = new_chunks[start : start + EMBEDDING_BATCH]

        # טקסט להטמעה: document דו-לשוני (מוכן מ-process_chunks.py)
        texts     = [c["document"] for c in batch]
        ids       = [c["id"]       for c in batch]
        metadatas = [sanitize_metadata(c["metadata"]) for c in batch]

        # הטמעה
        embeddings = embed_batch(model, texts)

        # הוספה ל-ChromaDB
        collection.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        added += len(batch)
        pbar.set_postfix(added=added, total=collection.count())

    pbar.close()
    log.info("✅ הושלם! %d וקטורים נוספו. סה\"כ ב-DB: %d", added, collection.count())

    # ── דוח סיכום ────────────────────────────────────────────────────────────
    print_summary(collection)


def print_summary(collection) -> None:
    """מדפיס דוח סיכום על ה-DB."""
    total = collection.count()
    print(f"\n{'─'*50}")
    print(f"  📊 סיכום Vector DB")
    print(f"{'─'*50}")
    print(f"  סה\"כ וקטורים: {total:,}")

    for ct in ["chumash", "rashi", "ramban"]:
        try:
            res = collection.get(where={"chunk_type": ct}, include=[])
            print(f"  {ct:<10}: {len(res['ids']):>6,} צ'אנקים")
        except Exception:
            pass
    print(f"{'─'*50}")


# ════════════════════════════════════════════════════════════════════════════════
# אימות
# ════════════════════════════════════════════════════════════════════════════════

def verify() -> None:
    """בודק שה-DB קיים ומריץ שאילתת ניסיון."""
    collection = get_collection()
    total = collection.count()
    log.info("DB קיים. סה\"כ וקטורים: %d", total)

    if total == 0:
        log.warning("ה-DB ריק!")
        return

    # שאילתות ניסיון
    test_queries = [
        "creation of the world",
        "What is the difference between Rashi and Ramban?",
        "Abraham and the covenant",
    ]

    print("\n=== שאילתות ניסיון ===")
    for q in test_queries:
        results = collection.query(
            query_texts=[q],
            n_results=3,
            include=["metadatas", "distances"],
        )
        print(f"\n🔍 '{q}'")
        for meta, dist in zip(results["metadatas"][0], results["distances"][0]):
            src  = f"{meta.get('book', '?')} {meta.get('chapter', '?')}:{meta.get('verse', '?')}"
            ct   = meta.get("chunk_type", "?").upper()
            cmt  = meta.get("commentator", "")
            tag  = f"{ct}/{cmt}" if cmt else ct
            print(f"   [{tag}] {src}  (distance={dist:.3f})")

    # סטטיסטיקות
    print_summary(collection)


# ════════════════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="בניית מסד נתונים וקטורי ל-Chavruta.AI")
    p.add_argument("--reset",  action="store_true", help="מחיקת DB קיים וחידוש מאפס")
    p.add_argument("--verify", action="store_true", help="בדיקת DB קיים + שאילתות ניסיון")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    print(f"\n{'═'*60}")
    print("  🗄️   Chavruta.AI — Vector DB Builder")
    print(f"{'═'*60}")
    print(f"  מודל:   {EMBEDDING_MODEL}")
    print(f"  DB:     {CHROMA_DB_PATH}")
    print(f"  Batch:  {EMBEDDING_BATCH}")
    print(f"  קלט:    {CHUNKS_FILE}")
    print(f"{'═'*60}\n")

    if args.verify:
        verify()
    else:
        build(reset=args.reset)


if __name__ == "__main__":
    main()
