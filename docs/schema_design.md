# תכנון סכמת נתונים — Chavruta.AI

> **גרסה:** 0.1 (PoC)
> **עודכן:** מאי 2026
> **מטרה:** הגדרת מבני הנתונים, אסטרטגיית ה-Chunking, ותצורת מסד הנתונים הוקטורי.

---

## 1. עקרון מרכזי: עיגון פסוק (Verse Anchoring)

כל פירוש (רש"י / רמב"ן) **מחובר** לפסוק המקורי שעליו הוא מפרש. זוהי ה**יחידה הסמנטית הבסיסית** של המערכת:

```
┌─────────────────────────────────────┐
│         VERSE ANCHOR UNIT           │
│                                     │
│  📖 פסוק: בראשית א:א               │
│     "בְּרֵאשִׁית בָּרָא אֱלֹהִים"  │
│                                     │
│     ├── 📝 רש"י:                    │
│     │    "לא היה צריך להתחיל..."    │
│     │                               │
│     └── 📜 רמב"ן:                   │
│          "אמר רבי יצחק..."          │
│          (בדרך כלל חולק / מרחיב)    │
└─────────────────────────────────────┘
```

**ה-`parent_verse_id`** (למשל `"Bereishit.1.1"`) הוא המפתח המשותף המקשר בין הפסוק לפירושיו במסד הנתונים.

---

## 2. אסטרטגיית Chunking

### 2.1 כללי החלוקה

| טיפוס | גודל צ'אנק | Overlap | הסבר |
|--------|-----------|---------|------|
| פסוק קצר (< 100 tokens) | פסוק שלם | אין | כל פסוק = צ'אנק אחד |
| פסוק ארוך (> 100 tokens) | 256 tokens | 50 tokens | חלוקה עם חפיפה לרצף |
| פירוש קצר (< 200 tokens) | פירוש שלם | אין | כל פירוש = צ'אנק אחד |
| פירוש ארוך (> 200 tokens) | 512 tokens | 50 tokens | חלוקה עם שמירת הקשר |

> **עברית:** ממוצע 4–5 תווים למילה; 512 tokens ≈ ~400 מילים ≈ ~2,000 תווים.

### 2.2 לוגיקת עיגון — Pseudo-code

```python
def create_chunks(verse: dict, rashi: str, ramban: str) -> list[dict]:
    chunks = []
    base_meta = {
        "book": verse["book"],
        "chapter": verse["chapter"],
        "verse": verse["verse"],
        "parent_verse_id": f"{verse['book']}.{verse['chapter']}.{verse['verse']}"
    }
    
    # צ'אנק 1: הפסוק עצמו
    chunks.append({
        **base_meta,
        "commentator": "chumash",
        "relationship": "verse",
        "text": verse["text"],
        "chunk_id": f"{verse['book']}_{verse['chapter']}_{verse['verse']}_verse"
    })
    
    # צ'אנקים לרש"י
    for i, chunk_text in enumerate(split_text(rashi, max_tokens=512, overlap=50)):
        chunks.append({
            **base_meta,
            "commentator": "rashi",
            "relationship": "comment_on",
            "text": chunk_text,
            "chunk_index": i,
            "chunk_id": f"{verse['book']}_{verse['chapter']}_{verse['verse']}_rashi_{i}"
        })
    
    # צ'אנקים לרמב"ן
    for i, chunk_text in enumerate(split_text(ramban, max_tokens=512, overlap=50)):
        chunks.append({
            **base_meta,
            "commentator": "ramban",
            "relationship": "comment_on",
            "text": chunk_text,
            "chunk_index": i,
            "chunk_id": f"{verse['book']}_{verse['chapter']}_{verse['verse']}_ramban_{i}"
        })
    
    return chunks
```

---

## 3. סכמת JSON מלאה לצ'אנק

```json
{
  "chunk_id":         "bereishit_1_1_rashi_0",
  "book":             "Bereishit",
  "book_he":          "בראשית",
  "book_num":         1,
  "parasha":          "Bereishit",
  "chapter":          1,
  "verse":            1,
  "verse_end":        1,
  "commentator":      "rashi",
  "source_id":        "Rashi on Bereishit.1.1",
  "parent_verse_id":  "Bereishit.1.1",
  "text_en":          "Said Rabbi Yitzchak: It was not necessary to begin...",
  "text_he":          "אָמַר רַבִּי יִצְחָק: לֹא הָיָה צָרִיךְ לְהַתְחִיל...",
  "chunk_index":      0,
  "total_chunks":     1,
  "relationship":     "comment_on",
  "token_count":      143,
  "char_count":       712,
  "source_url":       "https://www.sefaria.org/Rashi_on_Bereishit.1.1",
  "has_aramaic":      false,
  "created_at":       "2026-05-25T00:00:00Z"
}
```

---

## 4. מסד נתונים רלציוני — SQLite (Sidecar DB)

SQLite משמש כ**ארכיון רלציוני** לניהול יחסים בין פסוקים לפירושים, ולשאילתות מדויקות (לפי מספר פרק/פסוק).

### 4.1 טבלאות

```sql
-- טבלת פסוקים (anchor units)
CREATE TABLE verses (
    id          TEXT PRIMARY KEY,          -- "Bereishit.1.1"
    book        TEXT NOT NULL,             -- "Bereishit"
    book_he     TEXT NOT NULL,             -- "בראשית"
    book_num    INTEGER NOT NULL,          -- 1
    parasha     TEXT,                      -- "Bereishit"
    chapter     INTEGER NOT NULL,
    verse       INTEGER NOT NULL,
    text_en     TEXT,
    text_he     TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(book, chapter, verse)
);

-- טבלת פירושים
CREATE TABLE commentaries (
    id            TEXT PRIMARY KEY,        -- "bereishit_1_1_rashi_0"
    verse_id      TEXT NOT NULL,           -- FK → verses.id
    commentator   TEXT NOT NULL,           -- "rashi" | "ramban"
    chunk_index   INTEGER DEFAULT 0,
    total_chunks  INTEGER DEFAULT 1,
    text_en       TEXT,
    text_he       TEXT,
    token_count   INTEGER,
    has_aramaic   BOOLEAN DEFAULT FALSE,
    source_url    TEXT,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (verse_id) REFERENCES verses(id)
);

-- אינדקסים לשאילתות מהירות
CREATE INDEX idx_verses_book_chapter ON verses(book, chapter);
CREATE INDEX idx_commentaries_verse  ON commentaries(verse_id);
CREATE INDEX idx_commentaries_type   ON commentaries(commentator);
```

### 4.2 שאילתה לדוגמה — שליפת פסוק + פירושים
```sql
SELECT 
    v.text_en AS verse_text,
    c.commentator,
    c.text_en AS commentary_text
FROM verses v
JOIN commentaries c ON c.verse_id = v.id
WHERE v.book = 'Bereishit' 
  AND v.chapter = 1 
  AND v.verse = 1
ORDER BY c.commentator;
```

---

## 5. ChromaDB — מסד נתונים וקטורי

### 5.1 השוואה: ChromaDB vs FAISS

| קריטריון | ChromaDB | FAISS |
|----------|----------|-------|
| **Persistence** | ✅ מובנה (SQLite פנימי) | ❌ דורש שמירה ידנית |
| **Metadata Filtering** | ✅ `where={"commentator": "rashi"}` | ❌ אין תמיכה מובנית |
| **Python API** | ✅ פשוט ואינטואיטיבי | ⚠️ מורכב יותר |
| **ביצועים (100K vectors)** | ✅ מספיק ל-PoC | ✅ מהיר יותר בסדר גודל גדול |
| **תמיכת HNSW** | ✅ | ✅ |
| **התקנה** | `pip install chromadb` | `pip install faiss-cpu` |
| **המלצה** | **✅ לשלב PoC** | לגרסה מתקדמת |

### 5.2 קונפיגורציית ChromaDB

```python
import chromadb
from chromadb.config import Settings

# יצירת client עם persistence מקומי
client = chromadb.PersistentClient(
    path="./data/chroma_db",
    settings=Settings(
        anonymized_telemetry=False,
        allow_reset=True
    )
)

# יצירת collection עם הגדרות HNSW
collection = client.get_or_create_collection(
    name="chavruta_torah",
    metadata={
        "hnsw:space":           "cosine",     # מדד דמיון
        "hnsw:construction_ef": 100,           # איכות בנייה (גבוה = איכות גבוהה, איטי יותר)
        "hnsw:M":               16,            # קשרים בגרף (16 = איזון טוב)
        "hnsw:ef_search":       50,            # איכות חיפוש (ניתן להגדיל בזמן ריצה)
    }
)
```

### 5.3 מבנה ה-Collection

```
collection: "chavruta_torah"
│
├── ids:        ["bereishit_1_1_verse", "bereishit_1_1_rashi_0", ...]
│
├── documents:  ["In the beginning...", "Said Rabbi Yitzchak...", ...]
│               (טקסט אנגלי להטמעה; עברית ב-metadata)
│
├── embeddings: [[0.023, -0.441, 0.187, ...], ...]  ← 384 float32
│               (מחושב על-ידי bge-small-en-v1.5)
│
└── metadatas:  [
        {
            "book": "Bereishit",
            "chapter": 1,
            "verse": 1,
            "commentator": "chumash",
            "parent_verse_id": "Bereishit.1.1",
            "source_id": "Bereishit.1.1",
            "text_he": "בְּרֵאשִׁית בָּרָא אֱלֹהִים...",
            "relationship": "verse"
        },
        ...
    ]
```

### 5.4 שאילתות לדוגמה

```python
# שאילתה סמנטית כללית
results = collection.query(
    query_texts=["What is the difference between Rashi and Ramban on creation?"],
    n_results=5
)

# שאילתה עם סינון לפי מפרש
results = collection.query(
    query_texts=["creation of the world"],
    n_results=3,
    where={"commentator": {"$in": ["rashi", "ramban"]}}
)

# שאילתה עם סינון לפי ספר ופרק
results = collection.query(
    query_texts=["Abraham and the covenant"],
    n_results=5,
    where={
        "$and": [
            {"book": {"$eq": "Bereishit"}},
            {"chapter": {"$lte": 17}}
        ]
    }
)
```

---

## 6. אסטרטגיית Collection: אחד לכולם vs. מרובים

### אפשרות A — Collection יחיד (מומלץ לPoC)
```
"chavruta_torah" ← כל הטקסטים, סינון לפי metadata
```
**יתרונות:** פשוט, חיפוש אחיד על כל הקורפוס
**חסרונות:** פחות גמישות לאופטימיזציה עתידית

### אפשרות B — 3 Collections נפרדים
```
"chavruta_chumash"  ← פסוקים בלבד
"chavruta_rashi"    ← רש"י בלבד
"chavruta_ramban"   ← רמב"ן בלבד
```
**יתרונות:** חיפוש מהיר יותר כאשר הנושא ידוע
**חסרונות:** דורש ניהול מרובה, שאילתות cross-collection

**החלטה: אפשרות A עם metadata filtering** לשלב ה-PoC.

---

## 7. אבני בניין לשפה עברית/ארמית

### 7.1 אתגרי הטוקניזציה

| אתגר | הסבר |
|------|-------|
| **ניקוד** | ניקוד מלא (בראשִׁית) vs. כתיב חסר — יש לנרמל |
| **ארמית** | שכיחה ברש"י ורמב"ן (תרגום אונקלוס, גמרא) |
| **שמות עצם ייחודיים** | רש"י, רמב"ן, תוספות, ר"מ — חשוב ש-tokenizer יזהה |
| **אבריות** | ב', כ', ל', מ', ו', ה' — ידבקו למילה (בְּרֵאשִׁית = ב + ראשית) |

### 7.2 נורמליזציה של טקסט עברי

```python
import re
import unicodedata

def normalize_hebrew(text: str) -> str:
    """הסרת ניקוד וסימנים טעמיים לצורך הטמעה אחידה."""
    # טווח Unicode לניקוד עברי: U+0591–U+05C7
    text = re.sub(r'[֑-ׇ]', '', text)
    # נורמליזציה Unicode
    text = unicodedata.normalize('NFKC', text)
    # הסרת רווחים כפולים
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def clean_sefaria_html(text: str) -> str:
    """ניקוי תגיות HTML מ-Sefaria API."""
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    return text.strip()
```

### 7.3 מילון מונחים לשמירה כ-Special Tokens

```python
TORAH_SPECIAL_TOKENS = [
    # מפרשים ואישים
    "רש\"י", "רמב\"ן", "אבן עזרא", "רמב\"ם", "תוספות", "ר\"מ",
    # ספרים
    "בראשית", "שמות", "ויקרא", "במדבר", "דברים",
    # מונחים תלמודיים
    "תלמוד", "גמרא", "מדרש", "אגדה", "הלכה", "פשט", "דרש", "סוד", "רמז",
    # ביטויים ארמיים נפוצים
    "כד", "אמר", "אמרי", "תנא", "תניא", "איתא",
]
```

---

## 8. הערכת נפח נתונים

| מקור | מספר פסוקים | פירושים ממוצע/פסוק | צ'אנקים מוערכים |
|------|-------------|---------------------|-----------------|
| חמישה חומשים | ~5,845 | — | ~6,000 |
| רש"י | ~4,500 פירושים | ~1.2 | ~5,400 |
| רמב"ן | ~1,700 פירושים | ~2.5 (ארוך יותר) | ~4,250 |
| **סה"כ** | | | **~15,650 צ'אנקים** |

- **גודל מסד וקטורי:** ~15,650 × 384 × 4 bytes ≈ **~24MB** ← קטן מאוד ✅
- **זמן הטמעה (CPU):** ~15,650 ÷ 500 chunks/min ≈ **~31 דקות** ✅
