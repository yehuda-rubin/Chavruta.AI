# ═══════════════════════════════════════════════════════════════════════════════
# Chavruta.AI — Dataset Generator v3
# GPU: P100 16GB | מודל: Qwen2.5-3B-Instruct float16
# מייצר 2200 זוגות שאלה-תשובה לfine-tuning
# ═══════════════════════════════════════════════════════════════════════════════

# %% [markdown]
# ## שלב 0 — התקנות

# %% [code]
# !pip install transformers accelerate tqdm -q

# ═══════════════════════════════════════════════════════════════════════════════
# %% [markdown]
# ## שלב 1 — ייבואים והגדרות
# ═══════════════════════════════════════════════════════════════════════════════

# %% [code]
import json, random, re, os, time, logging
from pathlib import Path
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from tqdm import tqdm

# ── נתיבים ──────────────────────────────────────────────────────────────────
CHUNKS_FILE     = "/kaggle/input/datasets/yehudarubin/chavruta/all_chunks.json"
OUTPUT_FILE     = "/kaggle/working/chavruta_dataset_clean.jsonl"
CHECKPOINT_FILE = "/kaggle/working/checkpoint.json"
REPORT_FILE     = "/kaggle/working/generation_report.txt"
REJECT_LOG      = "/kaggle/working/rejected_samples.jsonl"

# ── מודל ────────────────────────────────────────────────────────────────────
MODEL_ID    = "Qwen/Qwen2.5-3B-Instruct"
TEMPERATURE = 0.1
MAX_NEW_TOKENS = 512
BATCH_SIZE  = 4   # P100 16GB — בטוח עם 3B float16

# ── ייצור ────────────────────────────────────────────────────────────────────
TOTAL_TARGET = 2200
SAVE_EVERY   = 100
WORKER_SPLIT = {          # פרופורציה לכל סוג
    "simple":      550,   # 25%
    "rashi":       550,   # 25%
    "ramban":      550,   # 25%
    "compare":     550,   # 25%
}

# ── System Prompt ────────────────────────────────────────────────────────────
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
log = logging.getLogger("chavruta")

# ═══════════════════════════════════════════════════════════════════════════════
# %% [markdown]
# ## שלב 2 — טעינת נתונים
# ═══════════════════════════════════════════════════════════════════════════════

# %% [code]
log.info("טוען צ'אנקים...")

with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
    raw = json.load(f)

raw_chunks = raw["chunks"]
log.info(f"נטענו {len(raw_chunks):,} צ'אנקים גולמיים")

# ── מיון צ'אנקים לפי פסוק ──────────────────────────────────────────────────
# ממיר מפורמט הDB לפורמט מאוחד לפי פסוק
verse_map = defaultdict(dict)   # {book.ch.vs: {chumash/rashi/ramban: chunk}}

for c in raw_chunks:
    meta = c["metadata"]
    key  = f"{meta['book']}.{meta['chapter']}.{meta['verse']}"
    ct   = meta["chunk_type"]
    verse_map[key][ct] = {
        "book":    meta["book"],
        "chapter": meta["chapter"],
        "verse":   meta["verse"],
        "text_he": meta.get("text_he", ""),
        "text_en": meta.get("text_en", ""),
        "full":    c["document"],
    }

log.info(f"פסוקים ייחודיים: {len(verse_map):,}")

# ── בניית רשימות לפי סוג עבודה ─────────────────────────────────────────────
simple_pool  = []   # פסוקים עם חומש
rashi_pool   = []   # פסוקים עם רש"י
ramban_pool  = []   # פסוקים עם רמב"ן
compare_pool = []   # פסוקים עם גם רש"י וגם רמב"ן

for key, verse in verse_map.items():
    if "chumash" in verse:
        simple_pool.append(key)
    if "rashi" in verse:
        rashi_pool.append(key)
    if "ramban" in verse:
        ramban_pool.append(key)
    if "rashi" in verse and "ramban" in verse:
        compare_pool.append(key)

log.info(f"simple={len(simple_pool):,} | rashi={len(rashi_pool):,} | "
         f"ramban={len(ramban_pool):,} | compare={len(compare_pool):,}")

# ═══════════════════════════════════════════════════════════════════════════════
# %% [markdown]
# ## שלב 3 — טעינת מודל (4-bit)
# ═══════════════════════════════════════════════════════════════════════════════

# %% [code]
log.info(f"טוען מודל: {MODEL_ID}")

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, padding_side="left")
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.float16,
    device_map="cuda",
    low_cpu_mem_usage=True,
)
model.eval()
log.info("✅ מודל נטען")

# ═══════════════════════════════════════════════════════════════════════════════
# %% [markdown]
# ## שלב 4 — פונקציות ייצור
# ═══════════════════════════════════════════════════════════════════════════════

# %% [code]

def build_messages(user_prompt: str) -> list[dict]:
    return [
        {"role": "system",    "content": SYSTEM_PROMPT},
        {"role": "user",      "content": user_prompt},
    ]


def batch_generate(prompts: list[str]) -> list[str]:
    """מייצר תשובות ל-batch של prompts בבת אחת."""
    all_messages = [build_messages(p) for p in prompts]
    texts = [
        tokenizer.apply_chat_template(m, tokenize=False, add_generation_prompt=True)
        for m in all_messages
    ]
    inputs = tokenizer(
        texts,
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=2048,
    ).to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            temperature=TEMPERATURE,
            do_sample=TEMPERATURE > 0,
            pad_token_id=tokenizer.pad_token_id,
        )

    results = []
    for i, out in enumerate(outputs):
        input_len = inputs["input_ids"].shape[1]
        decoded   = tokenizer.decode(out[input_len:], skip_special_tokens=True)
        results.append(decoded.strip())
    return results


# ─── בוני Prompt לפי סוג ────────────────────────────────────────────────────

def prompt_question_simple(verse_key: str) -> str:
    v = verse_map[verse_key]
    c = v.get("chumash", {})
    return (
        f"הנה פסוק מהתורה:\n"
        f"[{c['book']} {c['chapter']}:{c['verse']}]\n"
        f"{c.get('text_he', c.get('full', ''))[:400]}\n\n"
        f"צור שאלה ותשובה על פשט הפסוק.\n\n"
        f"פורמט חובה:\n"
        f"שאלה: [שאלה אחת ברורה על הפשט]\n"
        f"תשובה: [תשובה מפורטת בעברית]"
    )


def prompt_question_rashi(verse_key: str) -> str:
    v = verse_map[verse_key]
    r = v.get("rashi", {})
    c = v.get("chumash", {})
    pasuk = f"{r.get('book', c.get('book',''))} {r.get('chapter', c.get('chapter',''))}:{r.get('verse', c.get('verse',''))}"
    return (
        f"הנה פירוש רש\"י על {pasuk}:\n"
        f"{r.get('full', '')[:500]}\n\n"
        f"צור שאלה ותשובה על פירוש רש\"י.\n\n"
        f"פורמט חובה:\n"
        f"שאלה: [שאלה על פירוש רש\"י]\n"
        f"תשובה: [תשובה מבוססת על רש\"י בלבד]"
    )


def prompt_question_ramban(verse_key: str) -> str:
    v = verse_map[verse_key]
    r = v.get("ramban", {})
    c = v.get("chumash", {})
    pasuk = f"{r.get('book', c.get('book',''))} {r.get('chapter', c.get('chapter',''))}:{r.get('verse', c.get('verse',''))}"
    return (
        f"הנה פירוש רמב\"ן על {pasuk}:\n"
        f"{r.get('full', '')[:500]}\n\n"
        f"צור שאלה ותשובה על פירוש הרמב\"ן.\n\n"
        f"פורמט חובה:\n"
        f"שאלה: [שאלה על פירוש הרמב\"ן]\n"
        f"תשובה: [תשובה מבוססת על הרמב\"ן בלבד]"
    )


def prompt_question_compare(verse_key: str) -> str:
    v      = verse_map[verse_key]
    rashi  = v.get("rashi",  {})
    ramban = v.get("ramban", {})
    chumash = v.get("chumash", rashi)
    pasuk  = f"{chumash.get('book','')} {chumash.get('chapter','')}:{chumash.get('verse','')}"
    return (
        f"הנה פירושי רש\"י ורמב\"ן על {pasuk}:\n\n"
        f"רש\"י:\n{rashi.get('full', '')[:350]}\n\n"
        f"רמב\"ן:\n{ramban.get('full', '')[:350]}\n\n"
        f"צור שאלה השוואתית ותשובה.\n\n"
        f"פורמט חובה:\n"
        f"שאלה: [שאלה על ההבדל בין רש\"י לרמב\"ן]\n"
        f"תשובה: [הצג את שתי הדעות עם ציוני מקור]"
    )


WORKER_PROMPTS = {
    "simple":  (simple_pool,  prompt_question_simple),
    "rashi":   (rashi_pool,   prompt_question_rashi),
    "ramban":  (ramban_pool,  prompt_question_ramban),
    "compare": (compare_pool, prompt_question_compare),
}


# ═══════════════════════════════════════════════════════════════════════════════
# %% [markdown]
# ## שלב 5 — ולידציה
# ═══════════════════════════════════════════════════════════════════════════════

# %% [code]

def count_sentences(text: str) -> int:
    parts = re.split(r'[.!?。؟]\s*', text.strip())
    return len([p for p in parts if len(p.strip()) > 5])


def has_repetition(text: str, min_len: int = 8) -> bool:
    words = text.split()
    for size in range(3, 8):
        seen = set()
        for i in range(len(words) - size + 1):
            phrase = " ".join(words[i:i+size])
            if phrase in seen and len(phrase) >= min_len:
                return True
            seen.add(phrase)
    return False


def non_hebrew_ratio(text: str) -> float:
    if not text:
        return 1.0
    hebrew = sum(1 for c in text if 'א' <= c <= 'ת')
    non_heb = sum(1 for c in text if c.isalpha() and not ('א' <= c <= 'ת'))
    total = hebrew + non_heb
    return non_heb / total if total > 0 else 0.0


def validate(question: str, answer: str, worker_type: str) -> tuple[bool, str]:
    """מחזיר (תקין, סיבת_פסילה)."""

    # בדיקת עברית
    ratio = non_hebrew_ratio(answer)
    if ratio > 0.10:
        return False, f"יותר מ-10% תווים לא-עבריים ({ratio:.1%})"

    ratio_q = non_hebrew_ratio(question)
    if ratio_q > 0.10:
        return False, f"שאלה עם תווים לא-עבריים ({ratio_q:.1%})"

    # בדיקת אורך
    sentences = count_sentences(answer)
    if sentences < 4:
        return False, f"תשובה קצרה מדי ({sentences} משפטים)"
    if sentences > 15:
        return False, f"תשובה ארוכה מדי ({sentences} משפטים)"

    # בדיקת חזרות
    if has_repetition(answer):
        return False, "חזרה על ביטויים בתשובה"

    # בדיקת אזכור מפרש לפי סוג
    answer_lower = answer
    if worker_type == "rashi" and 'רש"י' not in answer_lower and "רשי" not in answer_lower:
        return False, "שאלת רש\"י ללא אזכור רש\"י בתשובה"
    if worker_type == "ramban" and 'רמב"ן' not in answer_lower and "רמבן" not in answer_lower:
        return False, "שאלת רמב\"ן ללא אזכור רמב\"ן בתשובה"
    if worker_type == "compare":
        has_rashi  = 'רש"י'  in answer_lower or "רשי"  in answer_lower
        has_ramban = 'רמב"ן' in answer_lower or "רמבן" in answer_lower
        if not (has_rashi and has_ramban):
            return False, "שאלה השוואתית ללא שני המפרשים"

    # בדיקת שאלה ריקה
    if len(question.strip()) < 10:
        return False, "שאלה קצרה מדי"

    return True, ""


def parse_qa(raw: str) -> tuple[str, str] | None:
    """מחלץ שאלה ותשובה מהפלט."""
    if "שאלה:" in raw and "תשובה:" in raw:
        try:
            q = raw.split("שאלה:", 1)[1].split("תשובה:", 1)[0].strip()
            a = raw.split("תשובה:", 1)[1].strip()
            return q, a
        except Exception:
            pass

    lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
    if len(lines) >= 2:
        q = lines[0].lstrip("•-?").strip()
        a = " ".join(lines[1:])
        return q, a

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# %% [markdown]
# ## שלב 6 — Checkpoint
# ═══════════════════════════════════════════════════════════════════════════════

# %% [code]

def load_checkpoint() -> dict:
    if Path(CHECKPOINT_FILE).exists():
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {t: 0 for t in WORKER_SPLIT}


def save_checkpoint(counts: dict):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(counts, f)


# ═══════════════════════════════════════════════════════════════════════════════
# %% [markdown]
# ## שלב 7 — לולאת ייצור
# ═══════════════════════════════════════════════════════════════════════════════

# %% [code]

# סטטיסטיקות
stats = {
    "generated":  0,
    "rejected":   0,
    "by_type":    Counter(),
    "rejections": Counter(),
    "start_time": datetime.now().isoformat(),
}

done_counts = load_checkpoint()
total_done  = sum(done_counts.values())
log.info(f"ממשיך מ-{total_done} רשומות קיימות: {done_counts}")

out_file    = open(OUTPUT_FILE, "a", encoding="utf-8")
reject_file = open(REJECT_LOG,  "a", encoding="utf-8")

pbar = tqdm(total=TOTAL_TARGET, initial=total_done, desc="מייצר זוגות")


def build_batch_for_worker(worker_type: str, n: int) -> list[tuple[str, str]]:
    """מכין batch של (verse_key, prompt) לworker מסוים."""
    pool, prompt_fn = WORKER_PROMPTS[worker_type]
    keys = random.sample(pool, min(n, len(pool)))
    return [(k, prompt_fn(k)) for k in keys]


try:
    while sum(done_counts.values()) < TOTAL_TARGET:

        # בחר worker שעדיין לא הגיע ליעד
        active_workers = [
            t for t, target in WORKER_SPLIT.items()
            if done_counts.get(t, 0) < target
        ]
        if not active_workers:
            break

        # בנה batch מעורב מכל ה-workers הפעילים
        batch_items = []
        for wtype in active_workers:
            remaining = WORKER_SPLIT[wtype] - done_counts.get(wtype, 0)
            n = min(BATCH_SIZE // len(active_workers), remaining)
            if n > 0:
                batch_items.extend([
                    (wtype, key, prompt_fn(key))
                    for key, prompt_fn in [(k, WORKER_PROMPTS[wtype][1])
                                           for k in random.sample(
                                               WORKER_PROMPTS[wtype][0],
                                               min(n, len(WORKER_PROMPTS[wtype][0]))
                                           )]
                ])

        if not batch_items:
            break

        # הכן prompts לbatch inference
        prompts    = [item[2] for item in batch_items]
        raw_outputs = batch_generate(prompts)

        # עבד תוצאות
        for (wtype, verse_key, _), raw in zip(batch_items, raw_outputs):
            parsed = parse_qa(raw)

            if not parsed:
                reason = "לא ניתן לחלץ שאלה/תשובה"
                stats["rejected"] += 1
                stats["rejections"][reason] += 1
                reject_file.write(json.dumps({
                    "type": wtype, "reason": reason, "raw": raw[:200]
                }, ensure_ascii=False) + "\n")
                continue

            question, answer = parsed
            valid, reason    = validate(question, answer, wtype)

            if not valid:
                stats["rejected"] += 1
                stats["rejections"][reason] += 1
                reject_file.write(json.dumps({
                    "type": wtype, "reason": reason,
                    "question": question[:100], "answer": answer[:100]
                }, ensure_ascii=False) + "\n")
                continue

            # ✅ רשומה תקינה
            record = {
                "messages": [
                    {"role": "system",    "content": SYSTEM_PROMPT},
                    {"role": "user",      "content": question},
                    {"role": "assistant", "content": answer},
                ],
                "metadata": {
                    "type":       wtype,
                    "verse_key":  verse_key,
                }
            }

            out_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            out_file.flush()
            stats["generated"] += 1
            stats["by_type"][wtype] += 1
            done_counts[wtype] = done_counts.get(wtype, 0) + 1

            pbar.update(1)
            pbar.set_postfix({
                "סוג": wtype,
                "✅": stats["generated"],
                "❌": stats["rejected"],
            })

        # שמור checkpoint כל 100 רשומות
        total_now = sum(done_counts.values())
        if total_now % SAVE_EVERY == 0 and total_now > total_done:
            save_checkpoint(done_counts)
            log.info(f"checkpoint נשמר — {total_now}/{TOTAL_TARGET}")
            total_done = total_now

except KeyboardInterrupt:
    log.info("עצר על ידי המשתמש")

finally:
    out_file.close()
    reject_file.close()
    pbar.close()
    save_checkpoint(done_counts)

log.info(f"✅ סיום ייצור — {stats['generated']} רשומות תקינות")


# ═══════════════════════════════════════════════════════════════════════════════
# %% [markdown]
# ## שלב 8 — דוח סיום
# ═══════════════════════════════════════════════════════════════════════════════

# %% [code]

end_time   = datetime.now().isoformat()
total_time = "N/A"

report_lines = [
    "═" * 60,
    "  Chavruta.AI — Generation Report",
    "═" * 60,
    f"  התחלה:      {stats['start_time']}",
    f"  סיום:        {end_time}",
    "",
    "  תוצאות:",
    f"  ✅ רשומות תקינות:  {stats['generated']:,}",
    f"  ❌ רשומות נפסלו:   {stats['rejected']:,}",
    f"  📊 אחוז הצלחה:     "
    f"{stats['generated']/(stats['generated']+stats['rejected'])*100:.1f}%"
    if (stats['generated'] + stats['rejected']) > 0 else "N/A",
    "",
    "  פירוט לפי סוג:",
]
for wtype, count in stats["by_type"].items():
    target = WORKER_SPLIT[wtype]
    pct    = count / target * 100 if target else 0
    report_lines.append(f"    {wtype:12s}: {count:4d}/{target} ({pct:.0f}%)")

report_lines += [
    "",
    "  סיבות פסילה:",
]
for reason, count in stats["rejections"].most_common(10):
    report_lines.append(f"    {count:4d}x  {reason}")

report_lines += [
    "",
    "  קבצי פלט:",
    f"    {OUTPUT_FILE}",
    f"    {REJECT_LOG}",
    "═" * 60,
]

report_text = "\n".join(report_lines)
print(report_text)

with open(REPORT_FILE, "w", encoding="utf-8") as f:
    f.write(report_text)

log.info(f"דוח נשמר: {REPORT_FILE}")


# %% [code]
# ── בדיקת דוגמה מהפלט ──────────────────────────────────────────────────────
print("\n--- דוגמה ראשונה ---")
with open(OUTPUT_FILE, encoding="utf-8") as f:
    first = json.loads(f.readline())

for msg in first["messages"]:
    role = msg["role"]
    content = msg["content"][:200]
    print(f"\n[{role.upper()}]\n{content}")
print(f"\nסוג: {first['metadata']['type']} | פסוק: {first['metadata']['verse_key']}")
