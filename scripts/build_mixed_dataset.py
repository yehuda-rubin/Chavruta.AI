# -*- coding: utf-8 -*-
"""
build_mixed_dataset.py
─────────────────────────────────────────────────────────────────────────
בונה דאטאסט מאוזן דו-לשוני (עברית + אנגלית) ל-LoRA על Qwen, מתוך
data/processed/all_chunks.json.

עיצוב:
  • זוגות חד-לשוניים  : שאלה עברית→תשובה עברית, שאלה אנגלית→תשובה אנגלית
    (מקבע "ענה בשפת השאלה" — קריטי לשופטים שבוחנים באנגלית).
  • זוגות דו-לשוניים  : מצטט את המקור בעברית + מסביר/מתרגם באנגלית
    (תחושת "רב" אמיתית + cross-lingual grounding). מינון נשלט.
  • ערבוב מוחלט (shuffle) עם seed קבוע → כל batch מכיל את שתי השפות.
  • פיצול train/val ברמת *פסוק* (group-aware) — מונע דליפה (leakage)
    של אותה תשובה בין train ל-val.

חוגות לכוונון בראש הקובץ:
  TARGET_EN_FRACTION   — None = השתמש בכל הנתונים (יחס ~50/50 טבעי).
                         0.6  = קצץ עברית ל-40% (אם רוצים הטיה לאנגלית).
  BILINGUAL_FRACTION   — שבר הפסוקים שגם מקבלים גרסה דו-לשונית.
  VAL_FRACTION         — שבר הפסוקים שמוחזקים ל-validation.
  SEED                 — seed לערבוב ולפיצול (שחזוריות מלאה).
"""

import json
import random
from collections import defaultdict
from pathlib import Path

# ─────────────────────────────────────────────
# חוגות לכוונון
# ─────────────────────────────────────────────
INPUT_JSON  = "data/processed/all_chunks.json"
OUT_DIR     = "data/processed"
OUT_TRAIN   = f"{OUT_DIR}/torah_mixed_train.jsonl"
OUT_VAL     = f"{OUT_DIR}/torah_mixed_val.jsonl"
OUT_STATS   = f"{OUT_DIR}/torah_mixed_stats.json"

TARGET_EN_FRACTION = None   # None = כל הנתונים (~50/50). אחרת קצץ עברית ליחס הזה.
BILINGUAL_FRACTION = 0.20   # 20% מהפסוקים מקבלים גם גרסה דו-לשונית
VAL_FRACTION       = 0.05   # 5% מהפסוקים מוחזקים ל-validation
SEED               = 42

# ─────────────────────────────────────────────
# System prompts
# ─────────────────────────────────────────────
SYSTEM_HE = """אתה תלמיד חכם ורב מומחה בתורה, בעל ידע עמוק ברש"י, רמב"ן ומפרשים נוספים.
אתה יודע להסביר גם לתלמיד מתחיל וגם לתלמיד חכם מנוסה.
אתה עונה בעברית תקנית וברורה, מתוך יראת שמים ואהבת תורה."""

SYSTEM_EN = """You are a Torah scholar and learned rabbi, deeply versed in Rashi, Ramban, and the classical commentators.
You can teach both the beginner and the advanced student.
You answer clearly and faithfully, always quoting the Hebrew source text and then explaining it."""

# ─────────────────────────────────────────────
# Question templates
# ─────────────────────────────────────────────
Q_HE = {
    "pasuk": [
        "מה כתוב בפסוק {ref}?",
        "תביא לי את הפסוק של {ref}",
        "מה לשון הפסוק ב{ref}?",
    ],
    "rashi": [
        'מה רש"י מפרש על {ref}?',
        'מה הסבר רש"י על הפסוק {ref}?',
        'תסביר לי את פירוש רש"י על {ref}',
        'מה אומר רש"י ב{ref}?',
    ],
    "ramban": [
        'מה הרמב"ן מפרש על {ref}?',
        'מה אומר הרמב"ן על {ref}?',
        'תסביר לי את פירוש הרמב"ן על {ref}',
        'מה גישת הרמב"ן ב{ref}?',
    ],
    "compare": [
        'מה ההבדל בין רש"י לרמב"ן על {ref}?',
        'איך רש"י והרמב"ן חלוקים על {ref}?',
        'תשווה בין רש"י לרמב"ן על {ref}',
    ],
}

Q_EN = {
    "pasuk": [
        "What does the verse {ref} say?",
        "Give me the text of {ref}",
        "What is written in {ref}?",
    ],
    "rashi": [
        "What does Rashi explain on {ref}?",
        "Explain Rashi's commentary on {ref}",
        "What does Rashi say on {ref}?",
        "How does Rashi interpret {ref}?",
    ],
    "ramban": [
        "What does Ramban explain on {ref}?",
        "What does Ramban say on {ref}?",
        "Explain Ramban's commentary on {ref}",
        "What is Ramban's approach on {ref}?",
    ],
    "compare": [
        "What is the difference between Rashi and Ramban on {ref}?",
        "How do Rashi and Ramban disagree on {ref}?",
        "Compare Rashi and Ramban on {ref}",
    ],
}

# שאלות דו-לשוניות: השאלה מבקשת מקור + הסבר, ולכן תשובה דו-לשונית היא התשובה הנכונה.
Q_BI = {
    "pasuk": [
        "Show me {ref} in Hebrew and explain what it means.",
        "תן לי את הפסוק {ref} במקור ותסביר אותו באנגלית.",
        "Quote {ref} in the original Hebrew, then translate it.",
    ],
    "rashi": [
        "Show Rashi on {ref} in the original and explain it in English.",
        "הבא את רש\"י על {ref} במקור ותסביר באנגלית.",
        "Quote Rashi on {ref} in Hebrew, then explain his comment.",
    ],
    "ramban": [
        "Show Ramban on {ref} in the original and explain it in English.",
        "הבא את הרמב\"ן על {ref} במקור ותסביר באנגלית.",
    ],
}

BOOK_MAP = {
    "Bereishit": "בראשית", "Shemot": "שמות", "Vayikra": "ויקרא",
    "Bamidbar": "במדבר",  "Devarim": "דברים",
}

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def ref_he(verse_id: str) -> str:
    p = verse_id.split(".")
    return f"{BOOK_MAP.get(p[0], p[0])} {p[1]}:{p[2]}"

def ref_en(verse_id: str) -> str:
    p = verse_id.split(".")
    return f"{p[0]} {p[1]}:{p[2]}"

def pair(system: str, question: str, answer: str, lang: str, ptype: str, verse: str) -> dict:
    return {
        "messages": [
            {"role": "system",    "content": system},
            {"role": "user",      "content": question},
            {"role": "assistant", "content": answer},
        ],
        "_lang": lang, "_type": ptype, "_verse": verse,
    }

def clean(s) -> str:
    return (s or "").strip()

# ─────────────────────────────────────────────
# Build
# ─────────────────────────────────────────────
def build():
    print(f"📖 reading: {INPUT_JSON}")
    data = json.load(open(INPUT_JSON, encoding="utf-8"))

    verses = defaultdict(dict)
    for c in data["chunks"]:
        m = c["metadata"]
        verses[m["verse_id"]][m["chunk_type"]] = c

    rng = random.Random(SEED)

    he_pairs, en_pairs, bi_pairs = [], [], []
    stats = defaultdict(int)

    for vid, ch in verses.items():
        rh, re_ = ref_he(vid), ref_en(vid)
        cu, ra, nb = ch.get("chumash"), ch.get("rashi"), ch.get("ramban")
        do_bi = rng.random() < BILINGUAL_FRACTION

        # texts
        p_he = clean(cu and cu["metadata"].get("text_he"))
        p_en = clean(cu and cu["metadata"].get("text_en"))
        r_he = clean(ra and ra["metadata"].get("commentary_text_he"))
        r_en = clean(ra and ra["metadata"].get("commentary_text_en"))
        n_he = clean(nb and nb["metadata"].get("commentary_text_he"))
        n_en = clean(nb and nb["metadata"].get("commentary_text_en"))

        # ── 1. פסוק ───────────────────────────────
        if p_he:
            for q in Q_HE["pasuk"]:
                he_pairs.append(pair(SYSTEM_HE, q.format(ref=rh), p_he, "he", "pasuk", vid))
        if p_en:
            for q in Q_EN["pasuk"]:
                en_pairs.append(pair(SYSTEM_EN, q.format(ref=re_), p_en, "en", "pasuk", vid))
        if do_bi and p_he and p_en:
            ans = f"{p_he}\n\nTranslation:\n{p_en}"
            bi_pairs.append(pair(SYSTEM_EN, rng.choice(Q_BI["pasuk"]).format(ref=re_), ans, "bi", "pasuk", vid))

        # ── 2. רש"י ───────────────────────────────
        if p_he and r_he:
            ans = f'הפסוק: {p_he}\n\nפירוש רש"י:\n{r_he}'
            for q in Q_HE["rashi"]:
                he_pairs.append(pair(SYSTEM_HE, q.format(ref=rh), ans, "he", "rashi", vid))
        if p_en and r_en:
            ans = f"The verse: {p_en}\n\nRashi's commentary:\n{r_en}"
            for q in Q_EN["rashi"]:
                en_pairs.append(pair(SYSTEM_EN, q.format(ref=re_), ans, "en", "rashi", vid))
        if do_bi and r_he and r_en:
            ans = f'רש"י (מקור):\n{r_he}\n\nExplanation (English):\n{r_en}'
            bi_pairs.append(pair(SYSTEM_EN, rng.choice(Q_BI["rashi"]).format(ref=re_), ans, "bi", "rashi", vid))

        # ── 3. רמב"ן ──────────────────────────────
        if p_he and n_he:
            ans = f'הפסוק: {p_he}\n\nפירוש רמב"ן:\n{n_he}'
            for q in Q_HE["ramban"]:
                he_pairs.append(pair(SYSTEM_HE, q.format(ref=rh), ans, "he", "ramban", vid))
        if p_en and n_en:
            ans = f"The verse: {p_en}\n\nRamban's commentary:\n{n_en}"
            for q in Q_EN["ramban"]:
                en_pairs.append(pair(SYSTEM_EN, q.format(ref=re_), ans, "en", "ramban", vid))
        if do_bi and n_he and n_en:
            ans = f'רמב"ן (מקור):\n{n_he}\n\nExplanation (English):\n{n_en}'
            bi_pairs.append(pair(SYSTEM_EN, rng.choice(Q_BI["ramban"]).format(ref=re_), ans, "bi", "ramban", vid))

        # ── 4. השוואה ─────────────────────────────
        if p_he and r_he and n_he:
            ans = f'הפסוק: {p_he}\n\nרש"י:\n{r_he}\n\nרמב"ן:\n{n_he}'
            for q in Q_HE["compare"]:
                he_pairs.append(pair(SYSTEM_HE, q.format(ref=rh), ans, "he", "compare", vid))
        if p_en and r_en and n_en:
            ans = f"The verse: {p_en}\n\nRashi:\n{r_en}\n\nRamban:\n{n_en}"
            for q in Q_EN["compare"]:
                en_pairs.append(pair(SYSTEM_EN, q.format(ref=re_), ans, "en", "compare", vid))

    # ── איזון יחס שפות ────────────────────────────
    if TARGET_EN_FRACTION is not None:
        # רוצים: |en| / (|en| + |he|) = TARGET_EN_FRACTION  → קצץ את הצד הגדול מדי
        target_he = int(len(en_pairs) * (1 - TARGET_EN_FRACTION) / TARGET_EN_FRACTION)
        if target_he < len(he_pairs):
            rng.shuffle(he_pairs)
            he_pairs = he_pairs[:target_he]

    all_pairs = he_pairs + en_pairs + bi_pairs
    rng.shuffle(all_pairs)

    # ── פיצול train/val ברמת פסוק (ללא דליפה) ──────
    all_verses = sorted(verses.keys())
    rng.shuffle(all_verses)
    n_val = int(len(all_verses) * VAL_FRACTION)
    val_verses = set(all_verses[:n_val])

    train = [p for p in all_pairs if p["_verse"] not in val_verses]
    val   = [p for p in all_pairs if p["_verse"] in val_verses]
    # ערבוב סופי אחרי הפיצול
    rng.shuffle(train)
    rng.shuffle(val)

    # ── סטטיסטיקה ─────────────────────────────────
    def tally(rows):
        d = defaultdict(int)
        for r in rows:
            d[f"lang:{r['_lang']}"] += 1
            d[f"type:{r['_type']}"] += 1
        return dict(d)

    n_he_final = sum(1 for p in all_pairs if p["_lang"] == "he")
    n_en_final = sum(1 for p in all_pairs if p["_lang"] in ("en", "bi"))
    stats_obj = {
        "seed": SEED,
        "target_en_fraction": TARGET_EN_FRACTION,
        "bilingual_fraction": BILINGUAL_FRACTION,
        "val_fraction": VAL_FRACTION,
        "totals": {
            "he_pairs": len(he_pairs), "en_pairs": len(en_pairs),
            "bi_pairs": len(bi_pairs), "all": len(all_pairs),
        },
        "language_balance": {
            "hebrew_pairs": n_he_final,
            "english_side_pairs": n_en_final,
            "english_pct": round(100 * n_en_final / max(1, len(all_pairs)), 1),
        },
        "split": {"train": len(train), "val": len(val), "val_verses": len(val_verses)},
        "train_breakdown": tally(train),
        "val_breakdown": tally(val),
    }

    # ── כתיבה (מסירים שדות _ פנימיים) ─────────────
    Path(OUT_DIR).mkdir(parents=True, exist_ok=True)
    def write(path, rows):
        with open(path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps({"messages": r["messages"]}, ensure_ascii=False) + "\n")

    write(OUT_TRAIN, train)
    write(OUT_VAL, val)
    json.dump(stats_obj, open(OUT_STATS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # ── דוח ───────────────────────────────────────
    print(f"\n{'='*55}")
    print(f"✅ total pairs: {len(all_pairs):,}")
    print(f"   🟦 Hebrew     : {len(he_pairs):,}")
    print(f"   🟥 English    : {len(en_pairs):,}")
    print(f"   🟪 Bilingual  : {len(bi_pairs):,}")
    print(f"\n🌐 language balance (English side counts bilingual):")
    print(f"   Hebrew : {n_he_final:,}  ({100-stats_obj['language_balance']['english_pct']:.1f}%)")
    print(f"   English: {n_en_final:,}  ({stats_obj['language_balance']['english_pct']:.1f}%)")
    print(f"\n📂 split (group-aware by verse, no leakage):")
    print(f"   train: {len(train):,}")
    print(f"   val  : {len(val):,}   ({len(val_verses):,} held-out verses)")
    print(f"\n💾 written:")
    print(f"   {OUT_TRAIN}")
    print(f"   {OUT_VAL}")
    print(f"   {OUT_STATS}")
    print(f"{'='*55}")


if __name__ == "__main__":
    if not Path(INPUT_JSON).exists():
        print(f"❌ not found: {INPUT_JSON} — run from the CHAVRUTA.AI project root")
    else:
        build()
