# 🕍 Chavruta.AI — עוזר לימוד תורה חכם

מערכת RAG מקומית לניתוח והשוואת פירושי **רש"י** ו**רמב"ן** על חמישה חומשי תורה.  
פועלת **לחלוטין מקומית** — ללא ענן, ללא API חיצוני.

---

## סטטוס נוכחי (מאי 2026)

| שלב | תיאור | סטטוס |
|-----|--------|--------|
| 0 | הכנת סביבה | ✅ הושלם |
| 1 | קליטת נתונים מ-Sefaria (5 ספרים) | ✅ הושלם |
| 2 | עיבוד ו-Chunking | ✅ הושלם — 15,274 צ'אנקים |
| 3 | בניית Vector DB | ⏳ רץ עכשיו — 11,360 צ'אנקים חדשים |
| 4 | RAG Pipeline | ✅ נכתב — `src/rag_pipeline.py` |
| 5 | ממשק Streamlit | ✅ נכתב — `app.py` |
| 6 | בדיקות ואופטימיזציה | ⬜ ממתין לסיום שלב 3 |

---

## נתוני מערכת

| ספר | פסוקים | רש"י | רמב"ן |
|-----|---------|------|--------|
| בראשית | 1,533 | 74.6% | 80.8% |
| שמות | 1,210 | 70.8% | 33.1% |
| ויקרא | 859 | 72.3% | 28.9% |
| במדבר | 1,288 | 53.3% | 18.6% |
| דברים | 956 | 69.7% | 33.5% |
| **סה"כ** | **5,846** | **73.8%** | **~48%** |

---

## דרישות מערכת

- Python 3.11+
- Ollama + `llama3.1` (`ollama pull llama3.1`)
- 16GB RAM, Intel i5 Gen 12+
- ללא GPU

---

## התקנה מהירה

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

---

## הרצה

```bash
# שלב 1: קליטת נתונים (כבר בוצע)
python scripts/fetch_sefaria.py

# שלב 2: עיבוד (כבר בוצע)
python scripts/process_chunks.py

# שלב 3: בניית Vector DB (כבר בוצע / רץ)
python scripts/build_vectordb.py

# שלב 4: CLI מצב שיחה
python src/rag_pipeline.py

# שלב 4: שאלה חד-פעמית
python src/rag_pipeline.py --query "מה אומר רש\"י על בריאת האור?"

# שלב 5: ממשק גרפי
streamlit run app.py
```

---

## Stack

| רכיב | טכנולוגיה |
|------|-----------|
| Embedding | `BAAI/bge-small-en-v1.5` (384 dim, CPU) |
| Vector DB | ChromaDB 1.x — HNSW cosine |
| LLM | Ollama + llama3.1 8B |
| UI | Streamlit |
| נתונים | Sefaria Open API |

---

## תיעוד

- [ארכיטקטורה](docs/architecture.md)
- [סכמת נתונים](docs/schema_design.md)
- [מפת דרכים](docs/roadmap.md)
