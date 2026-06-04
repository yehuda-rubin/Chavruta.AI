# ארכיטקטורת מערכת Chavruta.AI

> ⚠️ **מסמך היסטורי (Torah MVP).** מתאר את העיצוב המקומי המקורי (תורה בלבד, `bge-small-en` 384, ChromaDB).
> הארכיטקטורה הנוכחית — RAG על **כל התנ"ך**, `bge-m3` (1024), **Qdrant**, פרופיל offline/Nebius —
> נמצאת ב: [PLAN.md](PLAN.md) · [DECISIONS.md](DECISIONS.md) · [CORPUS.md](CORPUS.md).

> **גרסה:** 0.1 (PoC)
> **עודכן:** מאי 2026
> **מטרה:** הגדרת ארכיטקטורה מקצה-לקצה למערכת RAG מקומית ללימוד תורה עם פירושי רש"י ורמב"ן.

---

## 1. תיאור כללי

Chavruta.AI היא מערכת **Hybrid RAG (Retrieval-Augmented Generation)** הפועלת לחלוטין על חומרה מקומית. המערכת אינה מאמנת מודל מחדש, אלא משתמשת ב:

1. **מסד נתונים וקטורי** (ChromaDB) לאחסון קטעי טקסט מוטמעים מהתנ"ך ופירושיו.
2. **מנוע LLM מקומי** (Ollama + Llama-3-8B) לגנרציה של תשובות בהקשר רלוונטי.

---

## 2. זרימת נתונים — מקצה לקצה

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          CHAVRUTA.AI — DATA FLOW                            │
└─────────────────────────────────────────────────────────────────────────────┘

  ┌──────────────┐
  │ שאילתת משתמש │  ← "מה ההבדל בין רש"י לרמב"ן בפרשת בראשית א:א?"
  └──────┬───────┘
         │
         ▼
  ┌──────────────────────────┐
  │  [1] הטמעת שאילתה        │  ← bge-small-en-v1.5 / Dicta-BERT (CPU)
  │  Query Embedding         │    ייצור וקטור float32 בגודל 384 מימדים
  └──────┬───────────────────┘
         │
         ▼
  ┌──────────────────────────┐
  │  [2] חיפוש וקטורי         │  ← ChromaDB — cosine similarity
  │  Vector Search (k=5)     │    סינון לפי מטא-נתונים (ספר, פרק, פסוק, מפרש)
  └──────┬───────────────────┘
         │
         ▼
  ┌──────────────────────────────────────────────────────────┐
  │  [3] הרכבת הקשר (Context Assembly)                       │
  │                                                          │
  │  פסוק מקורי (תורה)                                       │
  │  ├── פירוש רש"י (Peshat — פשט)                           │
  │  └── פירוש רמב"ן (Derash/Kabbalah — נימוק/פולמוס ברש"י)  │
  └──────┬───────────────────────────────────────────────────┘
         │
         ▼
  ┌──────────────────────────┐
  │  [4] בניית פרומפט        │  ← Prompt Template (System + Context + Query)
  │  Prompt Construction     │    כולל הוראות: "השווה בין רש"י לרמב"ן..."
  └──────┬───────────────────┘
         │
         ▼
  ┌──────────────────────────┐
  │  [5] מנוע הסקה מקומי     │  ← Ollama HTTP API (localhost:11434)
  │  Ollama LLM (8B)         │    מודל: llama3.1 / Dicta-LM
  └──────┬───────────────────┘
         │
         ▼
  ┌──────────────────────────┐
  │  [6] תגובה + ציטוטים     │  ← JSON עם מקורות מצוינים (ספר/פרק/פסוק)
  │  Response + Citations    │
  └──────────────────────────┘
```

---

## 3. תיאור שכבות המערכת

### שכבה 1 — קליטת נתונים (Data Ingestion)
| רכיב | טכנולוגיה | תפקיד |
|------|-----------|--------|
| מקור נתונים | Sefaria Open API | שליפת תורה, רש"י, רמב"ן כ-JSON |
| עיבוד | Python + `requests` | ניקוי HTML, נורמליזציה של טקסט עברי |
| שמירה | JSON → SQLite | ארכיון גולמי לפני הטמעה |

**Endpoint לדוגמה:**
```
GET https://www.sefaria.org/api/texts/Bereishit.1.1?commentary=1
```

---

### שכבה 2 — הטמעה (Embedding Layer)
| פרמטר | ערך |
|--------|-----|
| מודל ראשי | `BAAI/bge-small-en-v1.5` (33M params) |
| חלופה עברית | `dicta-il/dictabert` |
| מימד וקטור | 384 |
| ביצועי CPU | ~500 chunks/min על i5-12th Gen |
| Batch Size | 32 (מותאם ל-16GB RAM) |
| ספרייה | `sentence-transformers` |

#### השוואת מודלי הטמעה

| מודל | גודל | שפות | זמן/1000 צ'אנקים (CPU) | איכות אנגלית | איכות עברית |
|------|------|------|------------------------|--------------|-------------|
| `bge-small-en-v1.5` | 33M | אנגלית | ~2 דקות | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| `paraphrase-multilingual-MiniLM` | 118M | 50+ שפות | ~6 דקות | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| `dicta-il/dictabert` | 110M | עברית | ~5 דקות | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| **המלצה PoC** | **bge-small** | | | **אנגלית תחילה** | |

> **הערה:** לשלב ה-PoC, מומלץ לעבוד עם הטקסט האנגלי של Sefaria ולהשתמש ב-`bge-small`. בגרסה מתקדמת יש לעבור ל-`dictabert` עם עברית מקורית.

---

### שכבה 3 — מסד נתונים וקטורי (Vector Database)
| פרמטר | ערך |
|--------|-----|
| מנוע | ChromaDB (persistent mode) |
| מיקום נתונים | `./data/chroma_db/` |
| אלגוריתם | HNSW (Hierarchical Navigable Small World) |
| מדד דמיון | Cosine Similarity |
| כמות צ'אנקים צפויה | ~15,000–25,000 (חמישה חומשים + רש"י + רמב"ן) |

---

### שכבה 4 — הרכבת הקשר (Context Assembly)
הלוגיקה המרכזית של המערכת: **חיבור פסוק + שני פירושים** לפרומפט אחד.

```python
# Pseudo-code
def assemble_context(query: str, results: list[dict]) -> str:
    context_blocks = []
    for chunk in results:
        if chunk["commentator"] == "chumash":
            context_blocks.append(f"[פסוק] {chunk['source_id']}: {chunk['text']}")
        elif chunk["commentator"] == "rashi":
            context_blocks.append(f"[רש\"י על {chunk['source_id']}]: {chunk['text']}")
        elif chunk["commentator"] == "ramban":
            context_blocks.append(f"[רמב\"ן על {chunk['source_id']}]: {chunk['text']}")
    return "\n\n".join(context_blocks)
```

---

### שכבה 5 — מנוע הסקה מקומי (Local LLM)
| פרמטר | ערך |
|--------|-----|
| פלטפורמה | Ollama (HTTP API, port 11434) |
| מודל ברירת מחדל | `llama3.1` (4.7GB GGUF) |
| חלופה | `llama3.1-q4_K_M` (קטן יותר) |
| Context Window | 8,192 tokens |
| זמן תגובה (CPU) | ~30-90 שניות לתגובה |
| Quantization | Q4_K_M / Q5_K_M (GGUF) |

---

## 4. סכמת מטא-נתונים

כל **צ'אנק** המאוחסן ב-ChromaDB כולל את מבנה המטא-נתונים הבא:

```json
{
  "chunk_id": "bereishit_1_1_rashi_chunk_0",
  "book": "Bereishit",
  "book_he": "בראשית",
  "parasha": "Bereishit",
  "chapter": 1,
  "verse": 1,
  "verse_end": 1,
  "commentator": "rashi",
  "source_id": "Rashi on Bereishit.1.1",
  "parent_verse_id": "Bereishit.1.1",
  "text_en": "In the beginning God created...",
  "text_he": "בְּרֵאשִׁית, בָּרָא אֱלֹהִים...",
  "chunk_index": 0,
  "total_chunks": 1,
  "relationship": "comment_on",
  "token_count": 187,
  "source_url": "https://www.sefaria.org/Rashi_on_Bereishit.1.1"
}
```

### ערכי `commentator`:
| ערך | משמעות |
|-----|--------|
| `"chumash"` | פסוק מקורי מהתורה |
| `"rashi"` | פירוש רש"י (על פשט הכתוב) |
| `"ramban"` | פירוש רמב"ן (עיון פילוסופי/קבלי, לרוב בדיון עם רש"י) |

### ערכי `relationship`:
| ערך | משמעות |
|-----|--------|
| `"verse"` | פסוק עצמאי |
| `"comment_on"` | פירוש המתייחס לפסוק אב (`parent_verse_id`) |

---

## 5. דיאגרמת רכיבים

```
┌─────────────────────────────────────────────────────────┐
│                   CHAVRUTA.AI COMPONENTS                 │
│                                                         │
│  ┌─────────────┐    ┌──────────────┐    ┌────────────┐  │
│  │  Sefaria    │    │  Embedding   │    │  ChromaDB  │  │
│  │  API Client │───▶│  Pipeline    │───▶│  (local)   │  │
│  │  (fetch)    │    │  bge-small   │    │  HNSW idx  │  │
│  └─────────────┘    └──────────────┘    └────┬───────┘  │
│                                              │           │
│  ┌─────────────┐    ┌──────────────┐    ┌────▼───────┐  │
│  │  Streamlit  │    │  RAG         │    │  Retriever │  │
│  │  UI (app)   │◀───│  Pipeline    │◀───│  (k=5)     │  │
│  │             │    │              │    │            │  │
│  └─────────────┘    └──────┬───────┘    └────────────┘  │
│                            │                            │
│                     ┌──────▼───────┐                    │
│                     │  Ollama      │                    │
│                     │  llama3.1 │                    │
│                     │  (local)     │                    │
│                     └──────────────┘                    │
└─────────────────────────────────────────────────────────┘
```

---

## 6. מגבלות חומרה ואסטרטגיות אופטימיזציה

| מגבלה | פתרון |
|--------|--------|
| אין GPU | GGUF quantization (Q4_K_M), CPU-optimized embeddings |
| 16GB RAM | Batch size 32, streaming inference ב-Ollama |
| מעבד i5-12th Gen | `sentence-transformers` עם `device='cpu'`, אינדוקס HNSW מוגבל |
| טקסט עברי/ארמי | `bge-small` עם טקסט אנגלי בשלב PoC; Dicta-BERT בהמשך |

---

## 7. קבצי מקור מרכזיים (מבנה מתוכנן)

```
chavruta.ai/
├── docs/
│   ├── architecture.md        ← קובץ זה
│   ├── schema_design.md
│   └── roadmap.md
├── scripts/
│   ├── fetch_sefaria.py        ← קליטת נתונים מ-API
│   ├── process_chunks.py       ← עיבוד וחלוקה לצ'אנקים
│   └── build_vectordb.py       ← הטמעה ובנייה ב-ChromaDB
├── src/
│   ├── rag_pipeline.py         ← לוגיקת RAG המרכזית
│   ├── prompt_builder.py       ← בניית פרומפטים
│   └── ollama_client.py        ← ממשק ל-Ollama API
├── data/
│   ├── raw/                    ← JSON גולמי מ-Sefaria
│   ├── processed/              ← צ'אנקים מעובדים
│   └── chroma_db/              ← מסד נתונים וקטורי
├── app.py                      ← Streamlit UI
└── requirements.txt
```
