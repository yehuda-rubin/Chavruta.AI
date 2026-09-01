# 008 — מצב ניתוח וליווי דפי מקורות (Source Sheet Companion)

**סטטוס / Status:** מתוכנן (Planned) — סגור לבטא פרטית (Private Beta Only).

---

## חלק א': עברית (Hebrew Specification)

### 1. מודל האינטראקציה והניתוב: קבצים מול שיחה (Script-First Routing)
המערכת פועלת במודל היברידי משולב:
1. **הפקת מסמך ליווי שלם וקבצים להורדה:** בהעלאה ראשונית של דף מקורות או בלחיצה על כפתור ייצוא ב-UI, המערכת מפיקה באופן דטרמיניסטי מסמך ליווי מקיף וקבצי Word (`.docx`) מעוצב RTL, PDF להדפסה, ו-Markdown.
2. **מנגנון ניתוב דו-שלבי (החלטה מתי לייצר קובץ מול שיחת צ'אט):**
   - **סקריפט דטרמיניסטי תחילה (Script-First):** העלאה ראשונית $\rightarrow$ תמיד קובץ; שאלת הבהרה רגילה $\rightarrow$ תמיד תשובת צ'אט מהירה (0ms השהייה, 0 עלות).
   - **זיהוי כוונת עריכה בשיחת המשך:** סקריפט Regex צר מזהה בקשות עריכה מפורשות (למשל: *"תבנה לי קובץ חדש"*, *"ערוך מחדש כחוברת"*).
   - **גיבוי מודל מהיר:** רק במקרים גבוליים, מודל קל (Classifier) מסווג האם להפיק קובץ מלא או להשיב בצ'אט.
3. **שיחת המשך אינטראקטיבית (Conversational Follow-up):** השיחה נשארת פעילה בדיוק כמו בספק [007](../007-lesson-followup-routing/plan.md) לדיון וחברותא על הדף.

---

### 2. מתודולוגיה פדגוגית תורנית
- **עץ הסתעפות מושגי (Thematic Branching):** זיהוי "החקירה המרכזית" (חפצא/גברא, סיבה/סימן) וחלוקת המקורות סביבה.
- **פתרון הפניות יחסיות:** תמיכה ב-"שם", "עיין שם", ודיבורי המתחיל בלבד (ד"ה).
- **זיהוי הערות עורך הדף:** התייחסות להערות מנחות של מחבר הדף כרמזים מכריעים למהלך.
- **תגיות תפקיד למקור:** `[מקור יסוד]`, `[קושיא]`, `[חידוש/סברא]`, `[ראיה]`, `[שיטה חולקת]`, `[הכרעה]`.
- **שאלות חברותא מדורגות:** פשט $\leftarrow$ השוואת שיטות $\leftarrow$ סברא והעמקה.

---

### 3. טיפול במקורות שאינם במאגר (Principle I — ללא הזיות)
- **מקור עם טקסט בדף:** ביאור אך ורק על בסיס הטקסט המועלה, עם תגית `[מקור מדף המשתמש — לא אומת מול מאגר חברותא]`.
- **מראה מקום בלבד ללא טקסט:** סימון שקוף כחסר `[מראה מקום שלא נמצא במאגר]`, ללא ניחוש תוכן הספר מהזיכרון.

---

### 4. ארכיטקטורת RAG, ביצועים ואבטחה
- **חילוץ מודע-מבנה:** תמיכה ב-PDF ב-2 טורים וטבלאות ב-Word.
- **Multi-Stage Background Job:** תהליך מדורג (חילוץ $\rightarrow$ הרחבת מקורות $\rightarrow$ ניתוח מקורות $\rightarrow$ חיבור המהלך $\rightarrow$ הפקת קבצים) למניעת Timeouts.
- **בקרת גישה (Gating):** סגור עבורך בלבד דרך `CHAVRUTA_SOURCE_SHEET_BETA_OWNERS`, `_is_admin`, ו-`devhelpers.has_feature(owner_id, "sourcesheet")`.
- **בסיס נתונים (SQLite Schema 32):** טבלת `saved_source_sheets` ושילוב ב-`purge_owner`.
- **חוויית משתמש (UX):** Stepped Progress Bar (25%, 50%, 75%, 100%), Split View בדסקטופ וטאבים במובייל.

---

## Part B: English (Engineering & Architectural Specification)

### 1. Hybrid Interaction Model & Script-First Routing Engine
1. **Initial Full Companion Guide & File Exports:** Ingesting a source sheet or clicking an export button deterministically generates the structured guide and downloadable formats (Styled RTL Word `.docx`, printable PDF, Markdown).
2. **Two-Stage Routing Engine (File Re-generation vs. Conversational Chat):**
   - **Script-First Determinism:** Initial ingestion $\rightarrow$ 100% full file; standard clarification questions $\rightarrow$ 100% fast conversational replies (0ms overhead, 0 extra tokens).
   - **Explicit Rebuild Recognition:** Targeted regex identifying explicit file/booklet generation requests during ongoing chat.
   - **Lightweight Model Fallback:** Fast classifier invoked only when intent is genuinely ambiguous.
3. **Interactive Follow-up Chat:** Consistent with Spec [007](../007-lesson-followup-routing/plan.md), the session remains active for interactive learning and inquiries regarding the sheet.

---

### 2. Advanced Rabbinic Pedagogy
- **Conceptual Branching Tree:** Reconstructing the core inquiry (חקירה) and mapping rabbinic opinions around it.
- **Relative Reference Resolver:** Contextual anaphora resolution for shorthand citations ("שם", "ע"ש", isolated dibur hamatchil headers).
- **Author Annotation Awareness:** Distinguishing sheet author notes from canonical sources to capture pedagogical intent.
- **Typology Badging:** `[Foundation]`, `[Challenge]`, `[Core Reasoning]`, `[Proof]`, `[Counter-Opinion]`, `[Ruling]`.
- **Tiered Chavruta Prompts:** Text comprehension $\rightarrow$ Comparative analysis $\rightarrow$ Conceptual synthesis.

---

### 3. Handling Unindexed Sources (Principle I)
- **Text provided in sheet:** Analyzed strictly based on uploaded text, badged as `[External User Source]`.
- **Bare reference with no text:** Explicitly flagged as unindexed without parametric hallucination.

---

### 4. RAG Architecture, Performance & Security
- **Layout-Aware Ingestion:** Multi-column PDF extraction and Word table processing.
- **Multi-Stage Background Job:** Map-Reduce async pipeline preventing timeouts and lost-in-the-middle phenomena.
- **Access Gate:** Restricted to admin/whitelist via `CHAVRUTA_SOURCE_SHEET_BETA_OWNERS`, `_is_admin`, and `devhelpers`.
- **Persistence:** `saved_source_sheets` table (SQLite Schema 32) with GDPR purge integration.
- **UX:** Stepped Progress feedback (25%, 50%, 75%, 100%), responsive Split View (Desktop) and tab navigation (Mobile).
