# סיכום סשן — 2026-07-12/13 · לולאת audit→תיקון→re-audit + הפרונטנד לאופליין

סשן אוטונומי ארוך: **4 סבבי ביקורת** (5/4 סוכנים כל אחד) → תיקון כל הממצאים → ביקורת חוזרת, עד
התכנסות. ~22 קומיטים, 198 טסטים ירוקים, הכול אומת חי מול הקורפוס (2.75M נקודות). ללא push, ללא
Nebius/API, בלי לגעת ב-chats/DB. גיבוי מלא (bundle + zip) נשמר ב-Downloads.

## שני הפתרונות הגדולים
1. **באג פורמט ה-refs בעיגון (השורש של אשכול בעיות האיכות).** הראוטר פולט `Genesis.1.1` (נקודות),
   הקורפוס שומר `Genesis 1.1` (רווח) → עיגון ה-named-ref החזיר 0 בשקט → הפסוק/דף הבסיסי מעולם לא
   עוגן, ובקורפוס הענק פרשנות קברה אותו. תוקן: `corpus/refs.py::canon_corpus_ref` + `with_ref_variants`
   (נקודה↔רווח · פרק→פסוק פותח · תלמוד amud→amud-linear), מוחל בנתיב העיגון ובריצפת המקור-היסודי.
2. **perek→daf** (הדוגמה המקורית). פיצחתי את מספור התלמוד של הקורפוס: `N = 2·דף − 1` (עמוד א) /
   `2·דף` (עמוד ב), והסגמנט 1:1 עם Sefaria. `scripts/build_talmud_perek_index.py` בונה אינדקס מ-Sefaria
   לכל 37 מסכתות הבבלי; `intents/landmarks.py` פותר `פרק <סדר/גימטריה/ספרה> ב<מסכת>`.
   **`פרק שלישי בסנהדרין` → `Sanhedrin 45.1` = "זה בורר"** — אומת חי.

## תיקונים לפי קטגוריה
**איכות שליפה:** weak-retrieval של חברותא (RRF מול סף קוסינוס) · ריצפת רעש per-hit (קוסינוס, שומר
לקסיקלי) · ריצפת base-source (מסונן unit_type=source, gated על קוסינוס אמיתי) · English landmarks
(word-boundary) · anchor-set מפורש (במקום `score>=1.0` שריצפה מוגברת/reranker היו שוברים).

**LLM / אג'נטי:** שליפה אג'נטית (`===NEED_SOURCES===`) הפכה בלתי-תלוית-backend (`llm/agentic.py`);
תוקנו 2 רגרסיות שיצרתי (generate לא-עטוף→500, race על fetched_sources → מוחזר per-call כ-tuple);
LLMBackend Protocol מכריז על `request`/`source_fetcher`.

**עמידות/אבטחה:** `retrieve` מתדרדר בחן על timeout של Qdrant · `_run_query` עוטף שגיאות (במקום 500,
שומר 4xx אמיתיים) · הגבלת אורך קלט · ברירת-מחדל `127.0.0.1` · "הודעת-שגיאה-כשיעור" נחסמה.

**תשתית:** אינדקס payload על ref/anchor_ref (`create_payload_indexes.py`) — מבטל timeout של 60ש'
ב-fetch_by_refs · **CI** (GitHub Actions על הטסטים ה-fake-backed).

## הפרונטנד — לאופליין מלא
ה-UI החי הוא הדף הסטטי `app/frontend/public/ui/chavruta.html` (העיצוב שאושר). הוסרה תלות ה-CDN:
Tailwind נבנה מקומית (v3 CLI מאותו config → `assets/chavruta.tw.css`, זהה למראה), הפונטים
self-hosted (`assets/fonts/`), והשורש (`index.html`) מפנה ל-UI. עובד ללא אינטרנט; ה-React SPA הישן
("נראה זוועה") לא מוגש יותר.

## תיעוד שעודכן
README (זרימת הארכיטקטורה, מצבים, שערי eval, bridge) · `docs/CORPUS.md §7` (אינדקסים + פורמט refs +
מספור amud-linear) · `app/frontend/README.md` (ה-UI הסטטי האופליין + rebuild) · CLAUDE.md · חוזה
pipeline-query (באנר "היסטורי חלקית") · `eval/tanakh_v1.jsonl` (סומן היסטורי — Tanakh-only).

## מה שנשאר (לא-מחייב, לא נוגע בסגנון השיעור שהמשתמש ביקש לשמר)
- איחוד פלט שני מנועי השיעור (`_run_lesson` מול `_lesson_answer`) — **הוחלט להשאיר את הסגנון הקיים**.
- דדופ קוד רינדור `[S#]` (משוכפל פי 4) — תחזוקתי בלבד.
- recall של שאלות חופשיות/אנגלית ללא landmark — עדיין קשה בקורפוס הענק (ריצפת base-source מקִלה).

## כללי-ברזל שנשמרו
🚫 ללא Nebius/API · ללא push ל-GitHub · בלי לגעת ב-chats/DB · לענות בעברית. תיעוד מלא בזיכרון הקבוע
(ראה `MEMORY.md`: `ref-format-anchoring`, `perek-reference-resolution-gap`, `agentic-bridge-retrieval`,
`qdrant-payload-index`, ...).
