# Chavruta.AI — Corpus Scope

היקף הטקסטים שהמערכת מאחזרת מהם. מקור: **Sefaria** (API + bulk export). כל טקסט נשמר
**בעברית ובאנגלית** (דרישה #5).

> **מצב נוכחי (עודכן 2026-06-29):** הקורפוס גדל מבסיס התנ"ך המאומת אל **כל ספריית Sefaria
> (14 קטגוריות)**. השליפה בצד שרת מתבצעת מ-**אינדקס Qdrant היברידי חי בן ~449k נקודות**
> (תנ"ך + משנה + תלמוד + שו"ת), וההלכה נטענת בהדרגה. ראה §0 ו-§6.

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

## 4. היקף (Scale)

| | תנ"ך (מאומת) | כלל הבית מדרש |
|---|---|---|
| פסוקים/קטעי-בסיס | 23,206 | מאות אלפים (לפי קטגוריה) |
| chunks | **126,738** | ההלכה לבדה ~594K; אינדקס חי ~449K נקודות |

הטמעת קורפוס בסדר גודל כזה = **Nebius embedding job** (חד-פעמי, pay-per-use) לכל קטגוריה.
מקומית ניתן להטמיע בהדרגה (קטגוריה-קטגוריה) על ה-CPU.

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

**דאטה לאימון LoRA:** [chavruta-torah-mixed](https://huggingface.co/datasets/Yehuda-Rubin/chavruta-torah-mixed).

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
