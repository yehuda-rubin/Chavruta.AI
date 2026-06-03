# מפת דרכים — Chavruta.AI

> **גרסה:** 0.3  
> **עודכן:** מאי 2026  
> **יעד:** PoC פונקציונלי → Fine-tuned model מותאם לתורה.

---

## סטטוס כולל

```
שלב 0   שלב 1   שלב 2   שלב 3   שלב 4   שלב 5   שלב 6   שלב 7    שלב 8
  ✅      ✅       ✅       ✅       ✅       ✅       ⏳       ⬜        ⬜
סביבה  נתונים  עיבוד  וקטורים   RAG      UI    בדיקות  Dataset  Fine-tune
```

---

## שלב 0 — הכנת סביבת פיתוח ✅

- Python 3.13, `.venv`
- `pip install -r requirements.txt` — כל הפקגים מותקנים
- Ollama מותקן + `llama3.1` (4.9GB, 128K context)
- ChromaDB, sentence-transformers, streamlit — מותקנים

**קבצים:** `requirements.txt`, `.venv/`

---

## שלב 1 — קליטת נתונים מ-Sefaria ✅

**5 ספרים הורדו ונשמרו ב-`data/raw/`:**

| ספר | קובץ | פסוקים | רש"י | רמב"ן |
|-----|------|---------|------|--------|
| בראשית | `bereishit.json` | 1,533 | 74.6% | 80.8% |
| שמות | `shemot.json` | 1,210 | 70.8% | 33.1% |
| ויקרא | `vayikra.json` | 859 | 72.3% | 28.9% |
| במדבר | `bamidbar.json` | 1,288 | 53.3% | 18.6% |
| דברים | `devarim.json` | 956 | 69.7% | 33.5% |
| **סה"כ** | | **5,846** | | |

**הערה:** רמב"ן אינו מפרש כל פסוק — חסרים הם נורמליים.

**קובץ:** `scripts/fetch_sefaria.py`

---

## שלב 2 — עיבוד ו-Chunking ✅

**פלט:** `data/processed/all_chunks.json` — 21.5MB

| ספר | פסוקים | חומש | רש"י | רמב"ן | סה"כ |
|-----|---------|------|------|--------|------|
| Bereishit | 1,533 | 1,533 | 1,143 | 1,238 | 3,914 |
| Shemot | 1,210 | 1,210 | 987 | 1,200 | 3,397 |
| Vayikra | 859 | 859 | 709 | 1,040 | 2,608 |
| Bamidbar | 1,288 | 1,288 | 749 | 798 | 2,835 |
| Devarim | 956 | 956 | 724 | 840 | 2,520 |
| **סה"כ** | **5,846** | **5,846** | **4,312** | **5,116** | **15,274** |

**אסטרטגיית Chunking:**
- מקסימום 512 טוקן (2048 תווים), overlap 50 טוקן
- `document` = כותרת + עברית מנוקדת + אנגלית (ביlingually ready לembedding)
- `chunk_type`: `chumash` | `rashi` | `ramban`
- פורמט ID: `Bereishit.1.1_rashi_0`

**קובץ:** `scripts/process_chunks.py`

---

## שלב 3 — בניית Vector DB ⏳ רץ עכשיו

**DB:** `data/chroma_db/` — ChromaDB persistent, HNSW cosine

**נכון לעכשיו:**
- בראשית: 3,914 וקטורים ✅ (הוטמע בשלב קודם)
- 4 ספרים נוספים: **רצים עכשיו** — 11,360 צ'אנקים בתהליך
- מודל: `BAAI/bge-small-en-v1.5` (384 dim, CPU)
- Batch: 32, ~355 batches, ~90 דקות סה"כ

**אחרי הסיום הצפוי:**
```
chumash : 5,846
rashi   : 4,312
ramban  : 5,116
סה"כ   : 15,274
```

**קובץ:** `scripts/build_vectordb.py`

**⚠️ לבדוק אחרי הסיום:**
- `python scripts/build_vectordb.py --verify`
- `python scripts/test_vectordb.py` — כל 5 הספרים

---

## שלב 4 — RAG Pipeline ✅ נכתב

**קובץ:** `src/rag_pipeline.py`

**מה יש:**
- `ChavrutaPipeline` class עם lazy loading
- `ask(query)` — שאלה מלאה → dict עם response + sources
- `stream(query)` — streaming token-by-token (לStreamlit)
- `retrieve(query, k)` — שליפה בלבד
- Multi-turn history (3 סיבובים)
- CLI מובנה: `python src/rag_pipeline.py`
- System prompt בעברית: "אתה חברותא"

**⚠️ לבדוק אחרי סיום שלב 3:**
1. Ollama רץ: `ollama serve`
2. `python src/rag_pipeline.py --query "מה אומר רש\"י על בריאת האור?"`
3. בדיקת streaming
4. בדיקת multi-turn

---

## שלב 5 — ממשק Streamlit ✅ נכתב

**קובץ:** `app.py`

**מה יש:**
- RTL מלא בעברית
- Streaming token-by-token
- פאנל מקורות (expander) עם ספר/פרק/פסוק + similarity
- Multi-turn היסטוריה
- Sidebar: top-k slider, בחירת מודל Ollama, כפתור טעינה
- מסך ריק עם שאלות לדוגמה

**הרצה:** `streamlit run app.py` → `localhost:8501`

**⚠️ לבדוק אחרי סיום שלב 3:**
1. `streamlit run app.py`
2. לחיצה על "טען מודל"
3. שאלה ראשונה בעברית
4. שאלה באנגלית
5. בדיקת streaming בממשק
6. בדיקת expander המקורות
7. בדיקת multi-turn

---

## שלב 6 — בדיקות ואופטימיזציה ⬜

**ממתין לסיום שלב 3.**

### רשימת בדיקות מלאה:

#### 6.1 Vector DB
- [ ] `python scripts/test_vectordb.py` — כל 5 הספרים
- [ ] בדיקת top-1 accuracy על שאלות ידועות
- [ ] בדיקת סינון לפי `chunk_type`

#### 6.2 RAG Pipeline
- [ ] 5 שאלות עברית — איכות תשובה
- [ ] 5 שאלות אנגלית — איכות תשובה
- [ ] שאלות השוואה רש"י↔רמב"ן
- [ ] מדידת זמן תגובה מקצה לקצה

#### 6.3 Streamlit App
- [ ] טעינה ראשונה — זמן
- [ ] Streaming — חלק או קופץ?
- [ ] RTL — תצוגה נכונה?
- [ ] Multi-turn — זוכר היסטוריה?

#### 6.4 אופטימיזציה אפשרית
- [ ] Ollama model: האם `llama3.1:8b-instruct-q4_K_M` מהיר יותר?
- [ ] top_k: 6 אופטימלי?
- [ ] Hybrid search: BM25 + vector?

---

---

## שלב 7 — בניית Dataset לאימון ⬜

### מטרה
יצירת 1,000–5,000 זוגות `{instruction, context, output}` לאימון מודל מותאם.

### אסטרטגיה: Synthetic Dataset מ-15,274 הצ'אנקים

**שלב א' — יצירת שאלות אוטומטית:**
```python
# scripts/generate_dataset.py
# עבור כל פסוק + רש"י + רמב"ן → שלח ל-Ollama → קבל שאלה + תשובה
template = """
בהינתן הפסוק והפירושים הבאים, צור שאלה ותשובה מדויקת בעברית:

[חומש] {chumash_text}
[רש"י] {rashi_text}
[רמב"ן] {ramban_text}

צור JSON: {{"question": "...", "answer": "..."}}
"""
```

**שלב ב' — סינון איכות:**
- הסרת תשובות קצרות מדי (< 50 מילה)
- הסרת כפילויות
- בדיקה ידנית על 100 דגימות

**פורמט פלט (Alpaca/ShareGPT):**
```json
{
  "instruction": "מה ההבדל בין רש\"י לרמב\"ן על בריאת האור?",
  "input": "[חומש] בראשית א:ג\n...\n[רש\"י]...\n[רמב\"ן]...",
  "output": "רש\"י מפרש...\nרמב\"ן לעומת זאת..."
}
```

**קובץ:** `scripts/generate_dataset.py`  
**פלט:** `data/training/chavruta_dataset.json`

---

## שלב 8 — Fine-tuning על Kaggle (חינם) ⬜

### מה Kaggle נותן בחינם
| משאב | כמות |
|------|------|
| GPU | 2× T4 (16GB VRAM כל אחד) |
| זמן/שבוע | 30 שעות GPU |
| RAM | 30GB |
| אחסון | 20GB |

→ **מספיק לחלוטין** ל-LoRA fine-tuning על llama3.1 8B.

### שיטה: LoRA עם Unsloth

**Kaggle Notebook:**
```python
# !pip install unsloth
from unsloth import FastLanguageModel

# טעינת מודל בסיס
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = "unsloth/Meta-Llama-3.1-8B-Instruct",
    max_seq_length = 4096,
    load_in_4bit = True,   # חוסך VRAM
)

# הוספת LoRA adapters
model = FastLanguageModel.get_peft_model(
    model,
    r = 16,              # rank — קטן יותר = מהיר יותר
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj"],
    lora_alpha = 16,
    lora_dropout = 0,
)

# אימון
trainer = SFTTrainer(
    model = model,
    train_dataset = dataset,   # chavruta_dataset.json
    max_seq_length = 4096,
    ...
)
trainer.train()

# שמירה ב-GGUF לOllama
model.save_pretrained_gguf("chavruta-llama3.1", tokenizer, quantization_method="q4_k_m")
```

### זמן אימון משוער על Kaggle T4
| Dataset | זמן |
|---------|-----|
| 1,000 דוגמאות | ~30 דקות |
| 3,000 דוגמאות | ~1.5 שעות |
| 5,000 דוגמאות | ~2.5 שעות |

### תהליך מלא
```
1. Kaggle → New Notebook → GPU T4 x2
2. העלאת chavruta_dataset.json
3. הרצת notebook האימון
4. הורדת chavruta-llama3.1.Q4_K_M.gguf
5. ollama create chavruta -f Modelfile
6. עדכון OLLAMA_MODEL = "chavruta" ב-rag_pipeline.py
```

### Modelfile לOllama
```
FROM ./chavruta-llama3.1.Q4_K_M.gguf
SYSTEM "אתה חברותא — עוזר לימוד תורה מומחה ברש\"י ורמב\"ן."
PARAMETER temperature 0.3
PARAMETER num_ctx 8192
```

---

## הרחבות עתידיות

| אפשרות | השפעה | מורכבות |
|--------|--------|---------|
| Dicta-BERT לembedding עברית | שיפור retrieval בעברית | בינונית |
| Hybrid Search (BM25 + Vector) | דיוק retrieval | בינונית |
| הוספת אבן עזרא, ספורנו | כיסוי רחב | נמוכה |
| תמיכה בגמרא, מדרש | הרחבת תחום | בינונית |
| v2: Fine-tuned + RAG ביחד | תשובות מדויקות מאוד | גבוהה |
