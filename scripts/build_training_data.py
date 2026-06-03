import json
from collections import defaultdict
from pathlib import Path

# ─────────────────────────────────────────────
# נתיבים — לפי מבנה הפרויקט שלך
# ─────────────────────────────────────────────

INPUT_JSON   = "data/processed/all_chunks.json"
OUTPUT_JSONL = "data/processed/torah_training_final.jsonl"

SYSTEM_PROMPT = """אתה תלמיד חכם ורב מומחה בתורה, בעל ידע עמוק ברש"י, רמב"ן ומפרשים נוספים.
אתה יודע להסביר גם לתלמיד מתחיל וגם לתלמיד חכם מנוסה.
אתה עונה בעברית תקנית וברורה, מתוך יראת שמים ואהבת תורה."""

QUESTION_TEMPLATES = {
    "pasuk": [
        "מה כתוב בפסוק {ref}?",
        "תביא לי את הפסוק של {ref}",
        "מה לשון הפסוק ב{ref}?",
    ],
    "rashi": [
        "מה רש\"י מפרש על {ref}?",
        "מה הסבר רש\"י על הפסוק {ref}?",
        "תסביר לי את פירוש רש\"י על {ref}",
        "מה אומר רש\"י ב{ref}?",
    ],
    "ramban": [
        "מה הרמב\"ן מפרש על {ref}?",
        "מה אומר הרמב\"ן על {ref}?",
        "תסביר לי את פירוש הרמב\"ן על {ref}",
        "מה גישת הרמב\"ן ב{ref}?",
    ],
    "compare": [
        "מה ההבדל בין רש\"י לרמב\"ן על {ref}?",
        "איך רש\"י והרמב\"ן חלוקים על {ref}?",
        "תשווה בין רש\"י לרמב\"ן על {ref}",
    ],
}

BOOK_MAP = {
    "Bereishit": "בראשית",
    "Shemot":    "שמות",
    "Vayikra":   "ויקרא",
    "Bamidbar":  "במדבר",
    "Devarim":   "דברים",
}

# ─────────────────────────────────────────────
# פונקציות עזר
# ─────────────────────────────────────────────

def format_ref(verse_id: str) -> str:
    parts = verse_id.split(".")
    book  = BOOK_MAP.get(parts[0], parts[0])
    return f"{book} {parts[1]}:{parts[2]}"

def make_pair(question: str, answer: str) -> dict:
    return {
        "messages": [
            {"role": "system",    "content": SYSTEM_PROMPT},
            {"role": "user",      "content": question},
            {"role": "assistant", "content": answer},
        ]
    }

# ─────────────────────────────────────────────
# המרה ראשית
# ─────────────────────────────────────────────

def convert(json_path: str, output_path: str):
    print(f"📖 קורא: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # קיבוץ chunks לפי verse_id
    verses = defaultdict(dict)
    for chunk in data["chunks"]:
        verse_id   = chunk["metadata"]["verse_id"]
        chunk_type = chunk["metadata"]["chunk_type"]
        verses[verse_id][chunk_type] = chunk

    pairs = []
    stats = defaultdict(int)

    # מעקב אחר כיסוי
    coverage = {
        "pasuk_only":        0,   # פסוק בלי שום פירוש
        "rashi_only":        0,   # פסוק + רש"י בלבד
        "ramban_only":       0,   # פסוק + רמב"ן בלבד
        "both":              0,   # פסוק + שניהם
    }

    for verse_id, chunks in verses.items():
        ref     = format_ref(verse_id)
        chumash = chunks.get("chumash")
        rashi   = chunks.get("rashi")
        ramban  = chunks.get("ramban")

        # ── מעקב כיסוי ──────────────────────────
        if chumash:
            has_r = bool(rashi and rashi["metadata"].get("commentary_text_he", "").strip())
            has_n = bool(ramban and ramban["metadata"].get("commentary_text_he", "").strip())
            if has_r and has_n:
                coverage["both"] += 1
            elif has_r:
                coverage["rashi_only"] += 1
            elif has_n:
                coverage["ramban_only"] += 1
            else:
                coverage["pasuk_only"] += 1

        # ── 1. שאלות על הפסוק — תמיד, לכל פסוק ──
        if chumash:
            text_he = chumash["metadata"]["text_he"].strip()
            if text_he:
                for q in QUESTION_TEMPLATES["pasuk"]:
                    pairs.append(make_pair(q.format(ref=ref), text_he))
                    stats["pasuk"] += 1

        # ── 2. שאלות על רש"י — גם בלי רמב"ן ──────
        if rashi and chumash:
            pasuk_he = chumash["metadata"]["text_he"].strip()
            rashi_he = rashi["metadata"].get("commentary_text_he", "").strip()
            if pasuk_he and rashi_he:
                answer = f"הפסוק: {pasuk_he}\n\nפירוש רש\"י:\n{rashi_he}"
                for q in QUESTION_TEMPLATES["rashi"]:
                    pairs.append(make_pair(q.format(ref=ref), answer))
                    stats["rashi"] += 1

        # ── 3. שאלות על רמב"ן — גם בלי רש"י ──────
        if ramban and chumash:
            pasuk_he  = chumash["metadata"]["text_he"].strip()
            ramban_he = ramban["metadata"].get("commentary_text_he", "").strip()
            if pasuk_he and ramban_he:
                answer = f"הפסוק: {pasuk_he}\n\nפירוש רמב\"ן:\n{ramban_he}"
                for q in QUESTION_TEMPLATES["ramban"]:
                    pairs.append(make_pair(q.format(ref=ref), answer))
                    stats["ramban"] += 1

        # ── 4. השוואה — רק כשיש שניהם ─────────────
        if rashi and ramban and chumash:
            pasuk_he  = chumash["metadata"]["text_he"].strip()
            rashi_he  = rashi["metadata"].get("commentary_text_he", "").strip()
            ramban_he = ramban["metadata"].get("commentary_text_he", "").strip()
            if pasuk_he and rashi_he and ramban_he:
                answer = (
                    f"הפסוק: {pasuk_he}\n\n"
                    f"רש\"י:\n{rashi_he}\n\n"
                    f"רמב\"ן:\n{ramban_he}"
                )
                for q in QUESTION_TEMPLATES["compare"]:
                    pairs.append(make_pair(q.format(ref=ref), answer))
                    stats["compare"] += 1

    # שמירה
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for pair in pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    # סטטיסטיקה מלאה
    print(f"\n{'='*50}")
    print(f"✅ סה\"כ pairs: {len(pairs):,}")
    print(f"\n📊 לפי סוג pair:")
    print(f"   📜 פסוקים:   {stats['pasuk']:,}")
    print(f"   📕 רש\"י:    {stats['rashi']:,}")
    print(f"   📗 רמב\"ן:   {stats['ramban']:,}")
    print(f"   ⚖️  השוואות: {stats['compare']:,}")
    print(f"\n📊 כיסוי פסוקים:")
    total_v = sum(coverage.values())
    print(f"   פסוק בלי פירוש:    {coverage['pasuk_only']:,}  ({coverage['pasuk_only']/total_v*100:.1f}%)")
    print(f"   פסוק + רש\"י בלבד: {coverage['rashi_only']:,}  ({coverage['rashi_only']/total_v*100:.1f}%)")
    print(f"   פסוק + רמב\"ן בלבד:{coverage['ramban_only']:,}  ({coverage['ramban_only']/total_v*100:.1f}%)")
    print(f"   פסוק + שניהם:      {coverage['both']:,}  ({coverage['both']/total_v*100:.1f}%)")
    print(f"   סה\"כ פסוקים:       {total_v:,}")
    print(f"\n💾 נשמר ל: {output_path}")
    print(f"{'='*50}")

# ─────────────────────────────────────────────
# הרצה
# ─────────────────────────────────────────────

if __name__ == "__main__":
    if not Path(INPUT_JSON).exists():
        print(f"❌ קובץ לא נמצא: {INPUT_JSON}")
        print(f"   הרץ מתוך תיקיית הפרויקט CHAVRUTA.AI")
    else:
        convert(INPUT_JSON, OUTPUT_JSONL)