"""
scripts/generate_dataset.py — Chavruta.AI
==========================================
יוצר dataset לאימון מודל מ-15,274 הצ'אנקים.

משתמש בכל 5,846 הפסוקים:
  • יש חומש + רש"י + רמב"ן → comparison / rashi / ramban
  • יש חומש + רש"י בלבד    → rashi
  • יש חומש + רמב"ן בלבד   → ramban
  • יש חומש בלבד            → chumash

תכונות:
  • Resume  — ממשיך מנקודת עצירה
  • Shuffle — כיסוי מגוון מכל 5 הספרים
  • שמירה  — כל 10 דוגמאות
  • log     — data/training/generate_dataset.log

הרצה:
  python scripts/generate_dataset.py
  python scripts/generate_dataset.py --model llama3.2 --target 5000
"""

from __future__ import annotations

import sys
import json
import random
import argparse
import logging
import time
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ─── נתיבים ──────────────────────────────────────────────────────────────────
CHUNKS_FILE  = ROOT / "data" / "processed" / "all_chunks.json"
OUTPUT_FILE  = ROOT / "data" / "training" / "chavruta_dataset.json"
LOG_FILE     = ROOT / "data" / "training" / "generate_dataset.log"

# ─── הגדרות ──────────────────────────────────────────────────────────────────
DEFAULT_MODEL  = "llama3.2"
DEFAULT_TARGET = 5000
SAVE_EVERY     = 10

# ─── Logging ─────────────────────────────────────────────────────────────────
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════════
# פרומפטים
# ════════════════════════════════════════════════════════════════════════════════

PROMPTS = {
    "comparison": """\
You are a Torah scholar. Based on the verse and commentaries below, write a question asking about the DIFFERENCE between Rashi and Ramban, and a detailed Hebrew answer (3-5 sentences). Be specific and cite the verse.

[{book} {chapter}:{verse}]
Verse: {chumash}
Rashi: {rashi}
Ramban: {ramban}

Return ONLY this JSON:
{{"question": "מה ההבדל בין רש\\"י לרמב\\"ן על הפסוק ב{book} {chapter}:{verse}?", "answer": "<תשובה מפורטת בעברית>"}}""",

    "rashi": """\
You are a Torah scholar. Based on the verse and Rashi's commentary below, write a question about what Rashi says, and a detailed Hebrew answer (3-5 sentences).

[{book} {chapter}:{verse}]
Verse: {chumash}
Rashi: {rashi}

Return ONLY this JSON:
{{"question": "מה מסביר רש\\"י על הפסוק ב{book} {chapter}:{verse}?", "answer": "<תשובה מפורטת בעברית>"}}""",

    "ramban": """\
You are a Torah scholar. Based on the verse and Ramban's commentary below, write a question about what Ramban says, and a detailed Hebrew answer (3-5 sentences).

[{book} {chapter}:{verse}]
Verse: {chumash}
Ramban: {ramban}

Return ONLY this JSON:
{{"question": "מה מסביר רמב\\"ן על הפסוק ב{book} {chapter}:{verse}?", "answer": "<תשובה מפורטת בעברית>"}}""",

    "chumash": """\
You are a Torah scholar. Based on the verse below, write a question about its meaning, and a detailed Hebrew answer (3-5 sentences).

[{book} {chapter}:{verse}]
Verse: {chumash}

Return ONLY this JSON:
{{"question": "מה משמעות הפסוק ב{book} {chapter}:{verse}?", "answer": "<תשובה מפורטת בעברית>"}}""",
}


# ════════════════════════════════════════════════════════════════════════════════
# עזרים
# ════════════════════════════════════════════════════════════════════════════════

def load_verses() -> list[dict]:
    """
    טוען all_chunks.json ומחזיר רשימת פסוקים עם כל התוכן הזמין.
    כולל את כל 5,846 הפסוקים (לא רק אלו עם שלושתם).
    """
    log.info("טוען צ'אנקים מ-%s ...", CHUNKS_FILE)
    raw    = json.loads(CHUNKS_FILE.read_text(encoding="utf-8"))
    chunks = raw.get("chunks", raw) if isinstance(raw, dict) else raw

    verses: dict[str, dict] = {}
    for c in chunks:
        meta  = c["metadata"]
        vid   = meta.get("verse_id", "")
        ctype = meta.get("chunk_type", "")
        if not vid:
            continue

        if vid not in verses:
            verses[vid] = {
                "verse_id": vid,
                "book":     meta.get("book", ""),
                "chapter":  str(meta.get("chapter", "")),
                "verse":    str(meta.get("verse", "")),
                "chumash":  "",
                "rashi":    "",
                "ramban":   "",
            }

        # שמור רק צ'אנק ראשון מכל סוג
        if meta.get("chunk_index", 0) == 0 and not verses[vid][ctype]:
            text = c["document"].split("\n", 1)[-1].strip()[:400]
            verses[vid][ctype] = text

    result = list(verses.values())
    log.info("סה\"כ פסוקים: %d", len(result))

    # סטטיסטיקות
    has_all  = sum(1 for v in result if v["chumash"] and v["rashi"] and v["ramban"])
    has_r    = sum(1 for v in result if v["chumash"] and v["rashi"] and not v["ramban"])
    has_rb   = sum(1 for v in result if v["chumash"] and not v["rashi"] and v["ramban"])
    has_c    = sum(1 for v in result if v["chumash"] and not v["rashi"] and not v["ramban"])
    log.info("  חומש+רש\"י+רמב\"ן: %d | +רש\"י: %d | +רמב\"ן: %d | חומש בלבד: %d",
             has_all, has_r, has_rb, has_c)
    return result


def get_question_types(verse: dict) -> list[str]:
    """מחזיר רשימת סוגי שאלות אפשריים לפי מה שיש בפסוק."""
    has_r  = bool(verse["rashi"])
    has_rb = bool(verse["ramban"])

    if has_r and has_rb:
        return ["comparison", "rashi", "ramban"]
    if has_r:
        return ["rashi"]
    if has_rb:
        return ["ramban"]
    return ["chumash"]


def load_existing() -> tuple[list[dict], set[str]]:
    """טוען dataset קיים לצורך resume."""
    if not OUTPUT_FILE.exists():
        return [], set()
    try:
        data     = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
        existing = data.get("data", [])
        done_ids = {e["verse_id"] + "_" + e.get("q_type", "") for e in existing}
        log.info("נמצאו %d דוגמאות קיימות — ממשיך מנקודת עצירה.", len(existing))
        return existing, done_ids
    except Exception:
        return [], set()


def save_dataset(data: list[dict], model: str) -> None:
    output = {
        "metadata": {
            "generated_at":   datetime.utcnow().isoformat(),
            "total_examples": len(data),
            "model_used":     model,
            "format":         "alpaca",
        },
        "data": data,
    }
    OUTPUT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def call_ollama(prompt: str, model: str) -> str | None:
    try:
        import ollama as ollama_lib
        response = ollama_lib.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.4, "num_ctx": 2048},
        )
        return response["message"]["content"].strip()
    except Exception as e:
        log.warning("שגיאת Ollama: %s", e)
        return None


def extract_json(text: str) -> dict | None:
    import re
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r'\{[^{}]*"question"[^{}]*"answer"[^{}]*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    return None


# ════════════════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════════════════

def generate(model: str, target: int) -> None:
    print(f"\n{'═'*60}")
    print(f"  🧠  Chavruta.AI — Dataset Generator")
    print(f"{'═'*60}")
    print(f"  מודל:   {model}")
    print(f"  יעד:    {target:,} דוגמאות")
    print(f"  פלט:    {OUTPUT_FILE}")
    print(f"{'═'*60}\n")

    # טעינת כל הפסוקים
    all_verses = load_verses()

    # בנה רשימת משימות: (verse, q_type)
    tasks = []
    for verse in all_verses:
        for qt in get_question_types(verse):
            tasks.append((verse, qt))

    random.seed(42)
    random.shuffle(tasks)
    log.info("סה\"כ משימות אפשריות: %d", len(tasks))

    # resume
    dataset, done_ids = load_existing()
    log.info("נותר לייצר: %d", max(0, target - len(dataset)))

    generated = 0
    errors    = 0
    t_start   = time.time()

    for verse, q_type in tasks:
        if len(dataset) >= target:
            break

        key = f"{verse['verse_id']}_{q_type}"
        if key in done_ids:
            continue

        # בניית פרומפט
        prompt = PROMPTS[q_type].format(
            book    = verse["book"],
            chapter = verse["chapter"],
            verse   = verse["verse"],
            chumash = verse["chumash"][:250],
            rashi   = verse["rashi"][:250],
            ramban  = verse["ramban"][:250],
        )

        t0  = time.time()
        raw = call_ollama(prompt, model)
        elapsed = round(time.time() - t0, 1)

        if not raw:
            errors += 1
            log.warning("[%s] אין תגובה", key)
            continue

        parsed = extract_json(raw)
        if not parsed or not parsed.get("question") or not parsed.get("answer"):
            errors += 1
            log.warning("[%s] JSON לא תקין: %s", key, raw[:80])
            continue

        # בדוק שהתשובה בעברית ולא ריקה
        answer = parsed["answer"].strip()
        if len(answer) < 30:
            errors += 1
            log.warning("[%s] תשובה קצרה מדי: %s", key, answer)
            continue

        entry = {
            "verse_id":    verse["verse_id"],
            "q_type":      q_type,
            "book":        verse["book"],
            "chapter":     verse["chapter"],
            "verse":       verse["verse"],
            "instruction": parsed["question"],
            "input": (
                f"[חומש] {verse['chumash'][:200]}\n"
                + (f"[רש\"י] {verse['rashi'][:200]}\n" if verse["rashi"] else "")
                + (f"[רמב\"ן] {verse['ramban'][:200]}" if verse["ramban"] else "")
            ).strip(),
            "output": answer,
        }

        dataset.append(entry)
        done_ids.add(key)
        generated += 1

        elapsed_total = int(time.time() - t_start)
        rate = generated / elapsed_total * 3600 if elapsed_total > 0 else 0
        eta  = int((target - len(dataset)) / (generated / elapsed_total)) if generated > 0 else 0

        log.info(
            "[%d/%d] %s %s:%s [%s] %.1fs | קצב: %.0f/שעה | ETA: %dד",
            len(dataset), target,
            verse["book"], verse["chapter"], verse["verse"],
            q_type, elapsed, rate, eta // 60,
        )

        if generated % SAVE_EVERY == 0:
            save_dataset(dataset, model)
            log.info("💾 נשמרו %d דוגמאות.", len(dataset))

    save_dataset(dataset, model)

    print(f"\n{'═'*60}")
    print(f"  ✅  הושלם!")
    print(f"  נוצרו:    {generated:,}")
    print(f"  שגיאות:   {errors:,}")
    print(f"  סה\"כ:     {len(dataset):,}")
    print(f"  קובץ:     {OUTPUT_FILE}")
    print(f"{'═'*60}\n")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model",  "-m", default=DEFAULT_MODEL)
    p.add_argument("--target", "-t", type=int, default=DEFAULT_TARGET)
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    generate(model=args.model, target=args.target)
