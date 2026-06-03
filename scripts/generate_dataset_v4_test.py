"""
generate_dataset_v4_test.py — Chavruta.AI Dataset Generator v4
===============================================================
מייצר 50 רשומות בדיקה עם RAG מלא (פסוק + רש"י + רמב"ן בקונטקסט).
הרץ מקומית עם qwen3.5:4b דרך Ollama.

שימוש:
    python scripts/generate_dataset_v4_test.py
פלט:
    data/dataset/test_50_samples.jsonl
"""

import json, random, re, sys, time, logging
from pathlib import Path
from collections import defaultdict

import ollama

# ── נתיבים ──────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent.parent
CHUNKS_FILE = BASE_DIR / "data" / "processed" / "all_chunks.json"
OUT_DIR     = BASE_DIR / "data" / "dataset"
OUT_FILE    = OUT_DIR  / "test_50_samples.jsonl"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── הגדרות ───────────────────────────────────────────────────────────────────
MODEL        = "qwen3.5:4b"
TARGET       = 50
TEMPERATURE  = 0.1
MAX_TOKENS   = 600

QUESTION_TYPES = ["simple", "rashi", "ramban", "compare"]
TYPE_WEIGHTS   = [0.25, 0.25, 0.25, 0.25]

SYSTEM_PROMPT = """אתה מומחה בתורה, רש"י ורמב"ן.
חוקים מוחלטים:
1. ענה רק בעברית בלבד — אסור מילה אחת בשפה אחרת
2. אם אינך יודע — אמור "אין לי מקור מספיק לכך"
3. אל תמציא פסוקים או פרשנויות שאינם קיימים
4. תשובה בין 4 ל-15 משפטים בלבד"""

# ── לוגינג ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("v4")


# ════════════════════════════════════════════════════════════════════════════
# טעינת נתונים
# ════════════════════════════════════════════════════════════════════════════

log.info("טוען צ'אנקים...")
with open(CHUNKS_FILE, encoding="utf-8") as f:
    raw = json.load(f)

# מאחד צ'אנקים לפי פסוק
verse_map = defaultdict(dict)
for c in raw["chunks"]:
    meta = c["metadata"]
    key  = f"{meta['book']}.{meta['chapter']}.{meta['verse']}"
    verse_map[key][meta["chunk_type"]] = {
        "book":    meta["book"],
        "chapter": meta["chapter"],
        "verse":   meta["verse"],
        "text_he": meta.get("text_he", ""),
        "full":    c["document"],
    }

# רשימות לפי סוג
simple_pool  = [k for k, v in verse_map.items() if "chumash" in v]
rashi_pool   = [k for k, v in verse_map.items() if "rashi"   in v]
ramban_pool  = [k for k, v in verse_map.items() if "ramban"  in v]
compare_pool = [k for k, v in verse_map.items() if "rashi"   in v and "ramban" in v]

log.info(f"פסוקים: {len(verse_map):,} | compare: {len(compare_pool):,}")


# ════════════════════════════════════════════════════════════════════════════
# בוני Prompt עם RAG מלא
# ════════════════════════════════════════════════════════════════════════════

def build_context(verse_key: str, qtype: str) -> str:
    """בונה קונטקסט מלא — פסוק + רש"י + רמב"ן לפי הצורך."""
    v     = verse_map[verse_key]
    parts = []

    chumash = v.get("chumash", {})
    rashi   = v.get("rashi",   {})
    ramban  = v.get("ramban",  {})

    ref = f"{chumash.get('book', rashi.get('book', ''))} " \
          f"{chumash.get('chapter', rashi.get('chapter', ''))}:" \
          f"{chumash.get('verse', rashi.get('verse', ''))}"

    if chumash:
        parts.append(f"📖 פסוק ({ref}):\n{chumash.get('text_he') or chumash.get('full','')[:400]}")

    if qtype in ("rashi", "compare") and rashi:
        parts.append(f"📝 רש\"י ({ref}):\n{rashi.get('full','')[:500]}")

    if qtype in ("ramban", "compare") and ramban:
        parts.append(f"📜 רמב\"ן ({ref}):\n{ramban.get('full','')[:500]}")

    # simple — הכל
    if qtype == "simple":
        if rashi:
            parts.append(f"📝 רש\"י ({ref}):\n{rashi.get('full','')[:300]}")
        if ramban:
            parts.append(f"📜 רמב\"ן ({ref}):\n{ramban.get('full','')[:300]}")

    return "\n\n".join(parts)


def build_user_prompt(verse_key: str, qtype: str) -> str:
    ctx = build_context(verse_key, qtype)

    instructions = {
        "simple": (
            "צור שאלה ותשובה על פשט הפסוק.\n"
            "שאלה: [שאלה על הפשט]\n"
            "תשובה: [תשובה מפורטת]"
        ),
        "rashi": (
            "צור שאלה ותשובה על פירוש רש\"י.\n"
            "שאלה: [שאלה על רש\"י]\n"
            "תשובה: [תשובה מבוססת על רש\"י בלבד]"
        ),
        "ramban": (
            "צור שאלה ותשובה על פירוש הרמב\"ן.\n"
            "שאלה: [שאלה על הרמב\"ן]\n"
            "תשובה: [תשובה מבוססת על הרמב\"ן בלבד]"
        ),
        "compare": (
            "צור שאלה השוואתית בין רש\"י לרמב\"ן.\n"
            "שאלה: [שאלה על ההבדל ביניהם]\n"
            "תשובה: [הצג את שתי הדעות עם ציוני מקור]"
        ),
    }

    return f"--- מקורות ---\n{ctx}\n\n--- משימה ---\n{instructions[qtype]}"


# ════════════════════════════════════════════════════════════════════════════
# ולידציה
# ════════════════════════════════════════════════════════════════════════════

def count_sentences(text: str) -> int:
    parts = re.split(r'[.!?]\s+', text.strip())
    return len([p for p in parts if len(p.strip()) > 5])


def non_hebrew_ratio(text: str) -> float:
    hebrew = sum(1 for c in text if 'א' <= c <= 'ת')
    non_heb = sum(1 for c in text if c.isalpha() and not ('א' <= c <= 'ת'))
    total = hebrew + non_heb
    return non_heb / total if total > 0 else 0.0


def validate(question: str, answer: str, qtype: str) -> tuple[bool, str]:
    if non_hebrew_ratio(answer) > 0.10:
        return False, "תווים לא-עבריים בתשובה"
    if non_hebrew_ratio(question) > 0.10:
        return False, "תווים לא-עבריים בשאלה"
    sentences = count_sentences(answer)
    if sentences < 4:
        return False, f"תשובה קצרה ({sentences} משפטים)"
    if sentences > 15:
        return False, f"תשובה ארוכה ({sentences} משפטים)"
    if len(question.strip()) < 10:
        return False, "שאלה קצרה מדי"
    if qtype == "rashi" and 'רש"י' not in answer and "רשי" not in answer:
        return False, "חסר אזכור רש\"י"
    if qtype == "ramban" and 'רמב"ן' not in answer and "רמבן" not in answer:
        return False, "חסר אזכור רמב\"ן"
    if qtype == "compare":
        if ('רש"י' not in answer and "רשי" not in answer) or \
           ('רמב"ן' not in answer and "רמבן" not in answer):
            return False, "חסר אחד המפרשים בהשוואה"
    return True, ""


def parse_qa(text: str) -> tuple[str, str] | None:
    if "שאלה:" in text and "תשובה:" in text:
        try:
            q = text.split("שאלה:", 1)[1].split("תשובה:", 1)[0].strip()
            a = text.split("תשובה:", 1)[1].strip()
            if len(q) > 10 and len(a) > 20:
                return q, a
        except Exception:
            pass
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) >= 2:
        return lines[0].lstrip("•-?").strip(), " ".join(lines[1:])
    return None


# ════════════════════════════════════════════════════════════════════════════
# ייצור
# ════════════════════════════════════════════════════════════════════════════

POOLS = {
    "simple":  simple_pool,
    "rashi":   rashi_pool,
    "ramban":  ramban_pool,
    "compare": compare_pool,
}

generated = 0
rejected  = 0
reject_reasons = defaultdict(int)

log.info(f"מתחיל ייצור {TARGET} רשומות עם {MODEL}...")
log.info("ודא ש-Ollama רץ: ollama serve")

out_file = open(OUT_FILE, "w", encoding="utf-8")

with open(OUT_FILE, "w", encoding="utf-8") as out_file:
    while generated < TARGET:
        qtype     = random.choices(QUESTION_TYPES, weights=TYPE_WEIGHTS)[0]
        pool      = POOLS[qtype]
        if not pool:
            continue
        verse_key = random.choice(pool)

        user_prompt = build_user_prompt(verse_key, qtype)

        try:
            response = ollama.chat(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
                options={
                    "temperature": TEMPERATURE,
                    "num_predict": MAX_TOKENS,
                },
            )
            raw = response["message"]["content"].strip()

        except Exception as e:
            log.error(f"שגיאת Ollama: {e}")
            time.sleep(3)
            continue

        parsed = parse_qa(raw)
        if not parsed:
            rejected += 1
            reject_reasons["parse_error"] += 1
            continue

        question, answer = parsed
        valid, reason    = validate(question, answer, qtype)

        if not valid:
            rejected += 1
            reject_reasons[reason] += 1
            log.debug(f"❌ {reason}")
            continue

        record = {
            "messages": [
                {"role": "system",    "content": SYSTEM_PROMPT},
                {"role": "user",      "content": question},
                {"role": "assistant", "content": answer},
            ],
            "metadata": {"type": qtype, "verse_key": verse_key},
        }
        out_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        out_file.flush()
        generated += 1

        log.info(f"[{generated:2d}/{TARGET}] ✅ {qtype} | {verse_key}")
        log.info(f"  שאלה:  {question[:80]}")
        log.info(f"  תשובה: {answer[:100]}...")
        log.info("")


# ════════════════════════════════════════════════════════════════════════════
# סיכום
# ════════════════════════════════════════════════════════════════════════════

log.info("═" * 50)
log.info(f"✅ נשמרו: {generated} רשומות → {OUT_FILE}")
log.info(f"❌ נפסלו: {rejected}")
if reject_reasons:
    log.info("  סיבות פסילה:")
    for r, n in sorted(reject_reasons.items(), key=lambda x: -x[1]):
        log.info(f"    {n}x  {r}")
log.info("═" * 50)
log.info("בדוק את הקובץ ידנית לפני שממשיכים!")
log.info(f"  {OUT_FILE}")
