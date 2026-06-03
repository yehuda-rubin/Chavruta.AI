"""
config.py — הגדרות מרכזיות של Chavruta.AI
"""
from pathlib import Path

BASE_DIR = Path(__file__).parent

# ── נתיבים ──────────────────────────────────────────────
DATA_RAW        = BASE_DIR / "data" / "raw"
DATA_PROCESSED  = BASE_DIR / "data" / "processed"
CHROMA_DB_PATH  = BASE_DIR / "data" / "chroma_db"
SQLITE_PATH     = BASE_DIR / "data" / "chavruta.db"

# ── Embedding ────────────────────────────────────────────
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_BATCH = 32

# ── ChromaDB ─────────────────────────────────────────────
COLLECTION_NAME = "chavruta_torah"
RETRIEVAL_TOP_K = 5

# ── Ollama ───────────────────────────────────────────────
OLLAMA_BASE_URL    = "http://localhost:11434"
OLLAMA_MODEL       = "qwen3.5:4b"
OLLAMA_TEMPERATURE = 0.3
OLLAMA_MAX_TOKENS  = 1024

# ── ספרים (חמישה חומשים) ────────────────────────────────
BOOKS = [
    {"en": "Genesis",      "sefaria": "Bereishit", "he": "בראשית"},
    {"en": "Exodus",       "sefaria": "Shemot",    "he": "שמות"},
    {"en": "Leviticus",    "sefaria": "Vayikra",   "he": "ויקרא"},
    {"en": "Numbers",      "sefaria": "Bamidbar",  "he": "במדבר"},
    {"en": "Deuteronomy",  "sefaria": "Devarim",   "he": "דברים"},
]
