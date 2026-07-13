# סיכום סשן — 2026-07-13 · ירושלמי לראג + מעבר ל-API (Qwen3-235B) + שרשרת תיקונים

סשן ארוך שהוסיף את **התלמוד הירושלמי** לקורפוס, העביר את המערכת (גם מקומית) ל-**API של Nebius**, וסגר
שרשרת באגים באיכות. ~20 קומיטים, 190 טסטי unit ירוקים. ללא push ל-GitHub.

## 1. התלמוד הירושלמי נוסף לראג 📖
היה חסר לגמרי (התלמוד היחיד היה `talmud_bavli`). כעת **שכבה 15: `talmud_yerushalmi`** — 188,079 chunks
(12,246 גמרא-בסיס + ~176K מפרשים: פני משה, קרבן העדה, ביאור הגר"א, מראה הפנים, אור לישרים, סיריליו,
רידב"ז…). הצינור:
- `scripts/fetch_full_dynamic.py --domain yerushalmi` — 39 מסכתות + כל המפרשים בגילוי דינמי (links API).
  Refs במבנה פרק:הלכה:קטע (`Jerusalem Talmud Bava Metzia 1.1.2`).
- אמבדינג ב-**Lightning** (`notebooks/embed_pipeline_lightning.ipynb`, `yerushalmi` ב-EXTRA_SOURCES;
  פינים `FlagEmbedding==1.3.4`/`transformers==4.44.2`) → פורסם ל-`chavruta-index-yerushalmi`.
- טעינה: `bootstrap_rag.py --repo …-yerushalmi --append` (server-mode env) + `create_payload_indexes.py`.
- אומת חי: הקולקציה עברה מ-2.75M ל-**2.93M נקודות**; שליפה מעלה לשון ירושלמי גולמי + מפרשיו.

**מאגרי HuggingFace (2):**
- מקור: [🤗 chavruta-torah-mixed](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-torah-mixed) (`yerushalmi_chunks.jsonl` וכו')
- אינדקס: [🤗 chavruta-index-yerushalmi](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-yerushalmi) (וכל `chavruta-index-*`)

## 2. מעבר ל-API של Nebius (גם מקומית) ☁️
הכלל הקשיח הקודם ("ללא API") **בוטל במפורש ע"י המשתמש**. `scripts/serve.ps1` = infra מקומי (CPU embedding
+ Qdrant מקומי) + **generation דרך Nebius**. מסע מודלים:
| מודל | מהירות | הכרעה |
|------|--------|-------|
| Llama-3.3-70B | 32ש' | חלש/קצר |
| GLM-5.2 | 146ש' | איכותי אך **נכשל בשיעורים** (timeout) |
| **Qwen/Qwen3-235B-A22B-Instruct-2507** ✅ | ~8ש' | חזק, ארוך, מהיר — **הנבחר** |

5 המצבים אומתו חיים דרך ה-API: שיעור · שאלה · הסבר · שו"ת · חברותא — כולם grounded ומצוטטים.

## 3. שרשרת התיקונים (הכל +טסטים)
**שליפה:**
- `CHAVRUTA_QUERY_PLANNER=heuristic` — ה-LLM planner הזה `named_refs` שגויים (בבא מציעא לנושא בסנהדרין)
  שצמצמו את השליפה למסכת הלא-נכונה → 0 מקורות.
- **fallback סמנטי**: scope שגוי (work/commentator) שמחזיר ריק → חיפוש לא-מסונן + ניקוי ה-scope
  (`hybrid.retrieve`). ref שגוי לעולם לא מאפס שליפה.
- **marker-poisoning**: `max_marker` סופר רק כותרות `### [S#]` (לא `[S#]` בטקסט המשתמש).
- **dense-only honesty gate** קורא קוסינוס גולמי (לא score מרוצף).

**לולאה אג'נטית:** בסבב האחרון מוכרחים תשובה במקום degrade (מודל ש-over-ask על מקורות מפוזרים).

**שיעורים / פלט:**
- **דף מקורות** נבנה תמיד מהטקסט המלא של המקורות מהראג (לא מהשחזור המקוצר "…") → ×8 גדול יותר.
- **אורך**: יעדי מילים מפורשים (בינוני 1600–2400, ארוך 3000–4500) + לחץ אנטי-סיכום.
- **מילים לועזיות**: חוקת "עברית בלבד" בכל הנתיבים + `_strip_foreign` (מסיר CJK/קירילי/ויאטנמי, שומר
  עברית דבוקה לתו זר).
- **qa** — פחות תמציתי ("ברור, מלא ומנומק").

**חברותא:** תוקן ה-stall — כשהשליפה טובה, הוראה חיובית "יש לך מקורות, קרא את הטקסט והתחל ללמוד, אל תבקש
דף"; "בקש הכוונה" הורד למוצא-אחרון אמיתי.

**עמידות:** double-checked lock על סינגלטונים (`_get_pipeline`/`_templates_client`).

## 4. הרצה
ראה `README.md → Run the full app`: Qdrant (docker) → `serve.ps1` (Nebius/Qwen) → `npm run dev` →
`http://localhost:5173/ui/chavruta.html`. הכיבוי: עצירת ה-tasks + `docker compose stop qdrant`.

## החלטות שנשמרו
🔑 גם מקומית משתמשים ב-API של Nebius · אורך שיעור מתקבל כמו שהוא · אין אופטימיזציית טוקנים כרגע · הכלל
"ללא API" בוטל. תיעוד בזיכרון: [[loaded-collection-tiers]], [[no-api-lesson-building]] (סומן מבוטל).
