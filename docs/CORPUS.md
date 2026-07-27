# Chavruta.AI — Corpus Scope

היקף הטקסטים שהמערכת מאחזרת מהם. מקור: **Sefaria** (API + bulk export). כל טקסט נשמר
**בעברית ובאנגלית** (דרישה #5).

> ## ⚠️ קולקציית הפרודקשן החליפה ל-`chavruta_commercial` (2026-07-20)
> הקולקציה החיה כעת היא **`chavruta_commercial`** — **2,403,599 נקודות**, 15 שכבות, **100% מסחרי**
> (PD/CC0/CC-BY/CC-BY-SA בלבד), on-disk (ssd). היא **דרסה** את `chavruta` הישן (המעורב). המסמך הזה
> מתאר את הקורפוס המלא/מעורב כ**רפרנס** — פרטי המהדורות המסחריות ב-`docs/COMMERCIAL_CORPUS.md`,
> והמצב החי ב-[[commercial-corpus-on-hf]].
> המספרים למטה (~2.93M, מאגרי `chavruta-index-<slug>`) מתייחסים לקורפוס המעורב הישן.
>
> **מצב היסטורי (עודכן 2026-07-13):** הקורפוס גדל מבסיס התנ"ך המאומת אל **כל ספריית Sefaria**.
> השליפה בצד שרת מתבצעת מ-**אינדקס Qdrant היברידי היה בן ~2.93M נקודות ב-15 שכבות (work_id)** —
> talmud_bavli · halacha · tanakh · mishnah · midrash · **talmud_yerushalmi (התלמוד הירושלמי + כל
> מפרשיו, נוסף 2026-07-13)** · chasidut · jewish_thought · responsa · liturgy · kabbalah · tosefta ·
> reference · musar · second_temple. שכבות חדשות נטענות בהדרגה (`bootstrap_rag.py --append`). ראה §0 ו-§6.

---

## 0. תמונת מצב — כל ספריית הבית מדרש

הטקסטים נמשכים מ-Sefaria דרך הסקריפטים `scripts/fetch_*.py`, מוטמעים ב-**Nebius GPU jobs**,
ומופצים כ-**מאגר Hugging Face לכל קטגוריה** (`chavruta-index-<slug>` — ראה
[memory: rag-index-distribution]). הטעינה ל-Qdrant היא תוספתית (verify → embed → upload → load)
ולא מוחקת את מה שכבר טעון.

| קטגוריה | מצב | היקף (משוער) |
|---------|-----|---------------|
| **תנ"ך** (Tanakh) | ✅ מוטמע ומאומת | 126,738 chunks (ראה §1–§2) |
| **משנה** (Mishnah) | ✅ נמשך + מוטמע | כל ששת הסדרים + מפרשים |
| **תלמוד בבלי** (Talmud) | ✅ נמשך + מוטמע (תיקון daf-shift) | כל הש"ס + רש"י/תוספות וכו' |
| **שו"ת** (Responsa) | ✅ נמשך + מוטמע | ~147K קטעים · 102 חיבורים |
| **הלכה** (Halacha) | ⏳ מוטמע, נטען בהדרגה | ~594,400 קטעים · 44 חלקים (שו"ע + מ"ב + …) |
| **מדרש, קבלה, מחשבה, ליטורגיקה, מוסר, דקדוק, ועוד** | ✅ נמשך (כל 14 הקטגוריות) | משתנה לפי קטגוריה |

> **קומנטרים מלאים:** תנ"ך/גמרא/משנה נמשכו מחדש עם **כל המפרשים שב-Sefaria**
> (`fetch_full_dynamic.py`) — פי ~2.5 מהמשיכה הראשונית.

---

## 1. כתבי הקודש — כל התנ"ך (24 ספרים) — הבסיס המאומת

| חלק | ספרים |
|-----|-------|
| **תורה** (5) | בראשית · שמות · ויקרא · במדבר · דברים |
| **נביאים** (8) | יהושע · שופטים · שמואל · מלכים · ישעיהו · ירמיהו · יחזקאל · תרי-עשר |
| **כתובים** (11) | תהילים · משלי · איוב · שיר השירים · רות · איכה · קהלת · אסתר · דניאל · עזרא-נחמיה · דברי הימים |

---

## 2. מפרשים ותרגומים (תנ"ך)

### תרגומים לארמית
| מפרש | כיסוי | הערה |
|------|-------|------|
| תרגום אונקלוס | תורה | התרגום הארמי הקלאסי |
| תרגום יונתן | נביאים | (וגם "יונתן" על התורה) |

### מפרשי הליבה
| מפרש | כיסוי עיקרי |
|------|-------------|
| רש"י | **כל התנ"ך** (תורה + רוב נ"ך) |
| רמב"ן | תורה (+ איוב) |
| אבן עזרא | תורה + חלקים נרחבים מנ"ך |
| בעל הטורים | תורה |
| ספורנו | תורה |
| **רשב"ם** | תורה — פשט קלאסי, משלים את רש"י |
| **אור החיים** | תורה — עומק ודרש |
| **רד"ק** | **נביאים + כתובים** (+תורה) — ⭐ המפרש המרכזי לנ"ך |
| **מלבי"ם** | **כל התנ"ך** (בעיקר נ"ך) |
| **מצודת דוד / ציון** | **נביאים + כתובים** — הפירוש הסטנדרטי ללימוד נ"ך |

כך מתקבל כיסוי מלא: רש"י/רשב"ם/אבן-עזרא/רמב"ן/ספורנו/בעה"ט/אוה"ח לתורה, ורד"ק/מצודות/מלבי"ם/רש"י לנ"ך.

---

## 3. זמינות ב-Sefaria ושליפה
- **Texts API** — `GET /api/v3/texts/{ref}` → טקסט עברי+אנגלי לכל הפניה.
- **Links API / Linker** — קישורים והפניות בין מקורות (לשכבת האחזור והרחבת הקישורים).
- **Bulk export** — מאגר Sefaria-Export (GitHub) להורדה חד-פעמית → תומך בפרופיל ה-offline (#8).
- כיסוי משתנה: לא לכל פסוק/קטע יש כל מפרש (למשל ספורנו/אוה"ח = תורה בלבד). זה תקין — מאחזרים מה שקיים.

---

## 4. היקף (Scale) — מספרים אמיתיים, נמדדו 2026-07-17

> ⚠️ **המספרים בסעיף הזה הם של הקורפוס המעורב-רישיון הישן (`chavruta`), שנמחק ב-2026-07-20.**
> **האינדקס החי היום הוא `chavruta_commercial` — 2,403,599 נקודות** (ראו הבאנר בראש הקובץ ו-§5).
> ההפרש הוא בדיוק המהדורות שאינן מסחריות ולכן הוצאו. הסעיף נשמר כי פילוח הכמויות לפי שכבה עדיין
> מלמד על יחסי הגודל בין הרבדים.

**האינדקס הישן (`chavruta`, נמחק):** 2,930,332 נקודות · 15 שכבות · **23.11GB על הדיסק**.

| | תנ"ך (מאומת) | כלל הבית מדרש |
|---|---|---|
| פסוקים/קטעי-בסיס | 23,206 | מאות אלפים (לפי קטגוריה) |
| chunks | 126,738 | **2,930,332 בקורפוס הישן שנמחק** (ההלכה לבדה ~594K) · החי: 2,403,599 |
| כותרות Sefaria ייחודיות | — | **17,561** |

### ⚠️ מה נדרש כדי לטעון את זה — קרא לפני שאתה מתחיל

הקורפוס **לא כלול בריפו ולא יורד אוטומטית**. `docker compose up` נותן Qdrant **ריק**;
`/ready` יחזיר 503 עם הסיבה עד שתטען.

| משאב | כמה | הערה |
|------|-----|------|
| **דיסק — האינדקס הסופי** | **~23GB** | נמדד על ה-volume החי (`qdrant_storage`) |
| **דיסק — בזמן הטעינה** | **+~20GB זמני** | `load_all_indexes.py` מוחק כל שכבה אחרי טעינתה כדי לפנות מקום לבאה — אל תסמוך על כך שיש לך רק 23GB פנויים |
| **הורדה** | **~20GB+** | מ-HuggingFace, פרוס על 15 מאגרים |
| **RAM** | **~16GB** (ברירת מחדל) | נשלט ב-`CHAVRUTA_MEM_TIER` — ראה `store/qdrant_store.py`: `16gb` / `32gb` / `max` |
| **זמן** | **שעות** | תלוי ברוחב פס; הטעינה **ניתנת להמשך** אחרי הפסקה |

**מבנה הווקטורים:** `dense` (1024 ממדים, Cosine, `on_disk=true`) + `sparse` — 6,113,687 וקטורים
מאונדקסים. אין קוונטיזציה כרגע; הפעלתה תקטין RAM על חשבון דיוק.

הטמעת קורפוס בסדר גודל כזה = **embedding job על GPU** (חד-פעמי, pay-per-use) לכל קטגוריה —
ראה `nebius/job.yaml` (~45-90 דק' על H100, ~$1-2). מקומית ניתן להטמיע בהדרגה על ה-CPU,
אבל זה איטי מאוד בקנה המידה הזה.

**אחרי הטעינה — שלב חובה:** `python scripts/create_payload_indexes.py`.
בלעדיו העיגון לפי ref נסרק במלואו ונתקע ב-timeout. ראה סעיף 7.

---

## 5. סקריפטי משיכה (scripts/)
- `fetch_corpus.py` — תנ"ך (הבסיס).
- `fetch_full_dynamic.py` — משיכה מחדש עם **כל** המפרשים של Sefaria. Domains: `tanakh`/`gemara`/`mishnah`
  ו-`yerushalmi` (**תלמוד ירושלמי** — 39 מסכתות + כל מפרשיו: פני משה, קרבן העדה, ביאור הגר"א, מראה
  הפנים, סיריליו, רידב"ז… → tier `talmud_yerushalmi`, קובץ `yerushalmi_chunks.jsonl`, מחברת אמבדינג
  `notebooks/embed_yerushalmi_kaggle.ipynb`). טען עם `load_to_store.py --no-recreate` (מוסיף שכבה, לא
  דורס), ואז `create_payload_indexes.py`.
- `fetch_category.py` — משיכת קטגוריה שלמה (כל 14 הקטגוריות).
- `fetch_mishnah.py` · `fetch_gemara.py` · `fetch_halacha.py` · `fetch_shut.py` — משיכות ייעודיות.
- `fix_daf_shift.py` — תיקון היסט הדף בתלמוד.

---

## 6. הפצה וטעינה (RAG Index Distribution)
1. לכל קטגוריה נבנה **מאגר HF נפרד** `chavruta-index-<slug>` (vectors + payload).
2. תהליך: **verify → embed (Nebius GPU) → upload (HF) → load (Qdrant server)**.
3. הטעינה תוספתית — לא מוחקת את מה שכבר באינדקס.
4. מדריך מלא לדוגמת ההלכה (בלי Docker): [NEBIUS_HALACHA_JOB.md](NEBIUS_HALACHA_JOB.md).

### מאגרי ה-HF (namespace: [🤗 Yehuda-Rubin](https://huggingface.co/Yehuda-Rubin))

אינדקסים מוכנים (datasets) — לטעינה ל-Qdrant ללא הטמעה מחדש:

| slug | מאגר |
|------|------|
| tanakh | [chavruta-index-tanakh](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-tanakh) |
| mishnah | [chavruta-index-mishnah](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-mishnah) |
| gemara | [chavruta-index-gemara](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-gemara) |
| shut | [chavruta-index-shut](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-shut) |
| halacha | [chavruta-index-halacha](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-halacha) |
| midrash | [chavruta-index-midrash](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-midrash) |
| kabbalah | [chavruta-index-kabbalah](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-kabbalah) |
| musar | [chavruta-index-musar](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-musar) |
| liturgy | [chavruta-index-liturgy](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-liturgy) |
| jewish_thought | [chavruta-index-jewish_thought](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-jewish_thought) |
| chasidut | [chavruta-index-chasidut](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-chasidut) |
| tosefta | [chavruta-index-tosefta](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-tosefta) |
| reference | [chavruta-index-reference](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-reference) |
| second_temple | [chavruta-index-second_temple](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-second_temple) |
| **talmud_yerushalmi** | [**chavruta-index-yerushalmi**](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-index-yerushalmi) (התלמוד הירושלמי + מפרשיו, 2026-07-13) |

**מאגר המקור (chunks גולמיים — `gemara_chunks.jsonl`, `yerushalmi_chunks.jsonl`, … + דאטה לאימון LoRA):**
[🤗 chavruta-torah-mixed](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-torah-mixed).

## 7. Serving prerequisites — payload indexes & ref format

After loading the collection into a Qdrant **server** (the full-scale hybrid mode), two things are
load-bearing for retrieval:

### 7.1 Keyword payload indexes (required)
Run once against the live collection:

```
python scripts/create_payload_indexes.py     # keyword indexes on ref + anchor_ref
```

Without them, `fetch_by_refs` (named-ref anchoring, link expansion, the lesson primary-source
floor) does a **full scan** of ~2.75M points and the Qdrant scroll **times out at 60s** → those
features silently degrade. `ensure_text_index` auto-creates only the `search_he` text index; the
`ref`/`anchor_ref` **keyword** indexes are NOT auto-created. Re-run the script whenever the
collection is rebuilt (indexes don't survive a fresh collection).

### 7.2 Reference format (dotted router refs vs space-form corpus refs)
The intent router emits **dotted** refs — `Genesis.1.1`, `Exodus.20`, `Bava Metzia.2a` — but the
corpus stores base-text `ref` payloads with a **space after the book name**: `Genesis 1.1`,
`Kiddushin 82.4`, `Mishnah Sukkah 3.5` (base Tanakh verses also carry `anchor_ref = null`;
`unit_type ∈ {source, commentary}`). An **exact** `MatchAny` lookup therefore needs the space form.
`corpus/refs.py::canon_corpus_ref` converts the book↔chapter dot to a space, and `with_ref_variants`
passes both spellings (plus the chapter→opening-verse `.1`); the retriever's anchoring path and the
lesson primary-source floor both use them. Do NOT confuse this with `canonical_ref`, the loose
lowercased join key used by the link graph. (There is no populated `search_he` payload field — its
lexical index is empty, so a `MatchText` on it will time out; the live path uses dense + `fetch_by_refs`.)

### 7.2b Empty payload fields — `commentator_id` and `anchor_ref` (measured 2026-07-27)

`chavruta_commercial` was indexed with **`commentator_id` empty and `anchor_ref` empty on all
2,403,599 points**. `unit_type` (`source`/`commentary`), `ref`, `work_id`, `lang` and `text` ARE
populated. Two consequences, both of which used to break named-commentator questions:

* a server-side filter on `commentator_id` matched **nothing**, so "what does Rashi say here" came
  back empty and was answered *"there is no Rashi in the corpus"* — with `Rashi_on_Genesis.1.1.1`
  sitting in the index;
* with `anchor_ref` empty, `fetch_by_refs("Genesis.1.1")` returns the **verse alone**, never its
  commentaries. Anchoring could not reach a commentary at all.

**Both are solved from the ref string, with no write to the collection.** Sefaria names a commentary
`<Title>_on_<Base>.<k>`, so `corpus/refs.py` reads it in both directions:

| direction | function | example |
|---|---|---|
| ref → commentator | `commentator_from_ref` | `Rashi_on_Genesis.1.1.1` → `rashi` |
| commentator → refs | `commentary_refs` | `Genesis.1.1` + `rashi` → `Rashi_on_Genesis.1.1.{1..8}` |

`retrieval/hybrid.py` derives the id on read (`_to_hit`) and anchors a named commentator by its own
**exact** ref, which the `ref` keyword index answers in milliseconds. Titles follow Sefaria's
capitalisation, not naive title-case (`or_hachaim` → `Or_HaChaim`), and Onkelos is filed as a plain
prefix with no `_on_` and no comment index (`Onkelos_Exodus.20.2`) — both handled explicitly.

**Why not backfill the fields?** It was tried. `set_payload` against the on-disk collection sustained
~5 points/sec — days for 2.4M, to store something a string split already yields. A ref that does not
exist simply returns nothing, so a commentator that genuinely has no comment here stays honestly
absent (Principle I). Verified live across Torah, Nach and Bavli: rashi, ramban, ibn_ezra, rashbam,
or_hachaim, sforno, malbim, radak, metzudat_david, metzudat_zion and onkelos all resolve.

### 7.3 Talmud amud-linear numbering & perek→daf

Talmud base texts are NOT stored with the amud letter. The corpus uses a FLAT amud-linear number:

```
corpus N = 2·daf − 1   (amud a)      # e.g. Sanhedrin 2a → 'Sanhedrin 3.1', 23a → 'Sanhedrin 45.1'
corpus N = 2·daf       (amud b)      # e.g. Berakhot 2b  → 'Berakhot 4.1'
```

and the within-amud segment index mirrors Sefaria's 1:1 (so Sefaria `Berakhot 17b:12` → corpus
`Berakhot 34.12`). The single source of truth for the formula is
`corpus/refs.py::daf_amud_to_corpus_n`; `with_ref_variants` converts an amud ref (`Sanhedrin.23a`)
to its corpus opening ref so explicit dapim, first-daf landmarks, and the perek resolver all anchor.

`scripts/build_talmud_perek_index.py` fetches every Bavli tractate's perek boundaries from Sefaria
(`alt_structs.Chapters`) and writes `src/chavruta/intents/data/talmud_perek_daf.json` (perek → opening
ref, in the corpus format above). `intents/landmarks.py` then resolves `פרק <ordinal|gematria|digit>
ב<מסכת>` → that ref. **Rebuild the JSON (`python scripts/build_talmud_perek_index.py`) if the corpus
ingest convention or Sefaria's perek structure changes.**

---

## 8. ⚠️ רישוי — הקורפוס אינו CC0

**אומת חי מול ה-API של Sefaria, 2026-07-17.** עד לתאריך זה `registry.py` הצהיר
`license="CC0 / Sefaria"` על **כל** הקורפוס. **זה היה שגוי.**

### המבנה שחייבים להפנים
Sefaria **לא** מרשה את הקורפוס ברישיון אחד. `Sefaria-Export/LICENSE.md` אומר זאת במפורש:
*"Each text is licensed separately... You can find the license for each text in their JSON versions
under the `license` field."*

**רישיון הוא פונקציה של `(title, language, versionTitle)`** — לא של היצירה, לא של המחבר,
ו**לא של ה-`work_id` שלנו**. אין שום חפיפה בין השכבות שלנו לגבולות הרישוי:

| טקסט | רישיון אמיתי |
|------|---------------|
| **Berakhot** (תלמוד, ברירת המחדל = William Davidson) | **CC-BY-NC** — בעברית **וגם** באנגלית |
| Berakhot — מהדורת A. Cohen, Cambridge | Public Domain ← **חלופה קיימת** |
| **Steinsaltz on Mishneh Torah** | **`Copyright: Steinsaltz Center`** — אין היתר CC כלל |
| **Peninei Halakhah, Berakhot** | **CC-BY-NC** (עברית) / **CC0** (אנגלית) ← אותה יצירה, שני רישיונות |
| רש"י, ביאור הגר"א, בית יוסף, כף החיים | Public Domain |

### מה זה אומר
- **שימוש חינמי / אישי / הוראה** — מותר. CC-BY-NC מתיר בדיוק את זה.
- **מוצר בתשלום שמשכפל טקסט NC** — **הפרה.** הניסוח של Creative Commons עצמם:
  *"charging for access may not be permitted with NC-licensed material."*
  NC חל על **השימוש**, לא על זהות המשתמש.
- **"unknown" או שדה חסר = כל הזכויות שמורות.** Sefaria עצמם לא אימתו את מעמדם.

### איך זה נאכף בקוד
- `src/chavruta/corpus/rights.py` — **המקום היחיד** שמסווג רישיון. **נכשל סגור:** כל מה שלא
  ניתן במפורש (PD / CC0 / CC-BY / CC-BY-SA) הוא "אסור מסחרית".
- `Chunk` / `RankedHit` / `CitationOut` נושאים `license` + `version_title`, **per שפה**.
- `fetch_full_dynamic.py` תופס אותם מהתשובה של Sefaria (הם תמיד היו שם — פשוט נזרקו).
- `scripts/backfill_licenses.py` מטביע אותם על הקורפוס החי דרך `set_payload` — **בלי embedding מחדש**
  (רישיון הוא metadata, לא משמעות; אף ווקטור לא משתנה).
- גיליון המקורות נותן ייחוס **TASL** (כותרת · מהדורה · מקור · רישיון) היכן שהרישיון דורש.
  ייחוס גנרי ל-"Sefaria" **אינו** מספיק ליצירת CC-BY של מתרגם או מו״ל ספציפי.

### לא נעשה — במודע
**החלפת טקסט NC במהדורות ה-PD שקיימות לצדו.** דורש שליפה מחדש עם `version=` מפורש
+ embedding מחדש של אותן שכבות (עבודת GPU). נדחה בהחלטה.

> **לפני גביית כסף — ייעוץ משפטי.** לא נמצא שום תקדים של מוצר בתשלום על קורפוס Sefaria;
> כל האפליקציות ב-"Powered by Sefaria" שנבדקו הן חינמיות. `sefaria.org/terms` הוא SPA ולא ניתן
> לקריאה אוטומטית — **צריך שאדם יקרא אותו בדפדפן.**
