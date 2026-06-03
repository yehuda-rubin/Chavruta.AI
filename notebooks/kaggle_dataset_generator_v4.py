# ═══════════════════════════════════════════════════════════════════════════════
# Chavruta.AI — Dataset Generator v4 (בדיקה)
# GPU: T4 x2 | מודל: Qwen2.5-4B-Instruct float16
# מייצר 50 רשומות בדיקה עם RAG מלא (פסוק + רש"י + רמב"ן)
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
import json, random, re, time, logging
from pathlib import Path
from collections import defaultdict, Counter

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from tqdm import tqdm

# ── נתיבים ──────────────────────────────────────────────────────────────────
CHUNKS_FILE  = "/kaggle/input/datasets/yehudarubin/chavruta/all_chunks.json"
OUTPUT_FILE  = "/kaggle/working/test_50_samples.jsonl"
REPORT_FILE  = "/kaggle/working/test_50_report.txt"

# ── מודל ────────────────────────────────────────────────────────────────────
MODEL_ID       = "Qwen/Qwen3.5-4B"
TEMPERATURE    = 0.1
MAX_NEW_TOKENS = 600
BATCH_SIZE     = 4

# ── ייצור ────────────────────────────────────────────────────────────────────
TARGET = 50
QUESTION_TYPES = ["simple", "rashi", "ramban", "compare"]
TYPE_WEIGHTS   = [0.25, 0.25, 0.25, 0.25]

# ── System Prompt ─────────────────────────────────────────────────────────
SYSTEM_PROMPT = """אתה מומחה בתורה, רש"י ורמב"ן.
חוקים מוחלטים:
1. ענה רק בעברית בלבד — אסור מילה אחת בשפה אחרת
2. אם אינך יודע — אמור "אין לי מקור מספיק לכך"
3. אל תמציא פסוקים או פרשנויות שאינם קיימים
4. תשובה בין 4 ל-15 משפטים בלבד"""

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("v4")

# ═══════════════════════════════════════════════════════════════════════════════
# %% [markdown]
# ## שלב 2 — טעינת נתונים
# ═══════════════════════════════════════════════════════════════════════════════

# %% [code]
log.info("טוען צ'אנקים...")
with open(CHUNKS_FILE, encoding="utf-8") as f:
    raw = json.load(f)

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

simple_pool  = [k for k, v in verse_map.items() if "chumash" in v]
rashi_pool   = [k for k, v in verse_map.items() if "rashi"   in v]
ramban_pool  = [k for k, v in verse_map.items() if "ramban"  in v]
compare_pool = [k for k, v in verse_map.items() if "rashi" in v and "ramban" in v]

log.info(f"פסוקים: {len(verse_map):,} | compare: {len(compare_pool):,}")

# ═══════════════════════════════════════════════════════════════════════════════
# %% [markdown]
# ## שלב 3 — טעינת מודל
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
# ## שלב 4 — פונקציות RAG + ייצור
# ═══════════════════════════════════════════════════════════════════════════════

# %% [code]

POOLS = {
    "simple":  simple_pool,
    "rashi":   rashi_pool,
    "ramban":  ramban_pool,
    "compare": compare_pool,
}

def build_full_context(verse_key: str, qtype: str) -> str:
    """RAG מלא — פסוק + רש"י + רמב"ן לפי סוג השאלה."""
    v       = verse_map[verse_key]
    chumash = v.get("chumash", {})
    rashi   = v.get("rashi",   {})
    ramban  = v.get("ramban",  {})

    book = (chumash or rashi or ramban).get("book", "")
    ch   = (chumash or rashi or ramban).get("chapter", "")
    vs   = (chumash or rashi or ramban).get("verse", "")
    ref  = f"{book} {ch}:{vs}"

    parts = []

    if chumash:
        text = chumash.get("text_he") or chumash.get("full", "")
        parts.append(f"📖 פסוק ({ref}):\n{text[:500]}")

    if qtype in ("rashi", "compare", "simple") and rashi:
        parts.append(f'📝 רש"י ({ref}):\n{rashi.get("full","")[:600]}')

    if qtype in ("ramban", "compare", "simple") and ramban:
        parts.append(f'📜 רמב"ן ({ref}):\n{ramban.get("full","")[:600]}')

    return "\n\n".join(parts)


def build_user_prompt(verse_key: str, qtype: str) -> str:
    ctx = build_full_context(verse_key, qtype)

    task = {
        "simple":  (
            "צור שאלה ותשובה על פשט הפסוק.\n\n"
            "פורמט חובה:\n"
            "שאלה: [שאלה אחת על הפשט]\n"
            "תשובה: [תשובה מפורטת]"
        ),
        "rashi": (
            'צור שאלה ותשובה על פירוש רש"י.\n\n'
            "פורמט חובה:\n"
            'שאלה: [שאלה על רש"י]\n'
            'תשובה: [תשובה מבוססת על רש"י בלבד]'
        ),
        "ramban": (
            'צור שאלה ותשובה על פירוש הרמב"ן.\n\n'
            "פורמט חובה:\n"
            'שאלה: [שאלה על הרמב"ן]\n'
            'תשובה: [תשובה מבוססת על הרמב"ן בלבד]'
        ),
        "compare": (
            'צור שאלה השוואתית בין רש"י לרמב"ן.\n\n'
            "פורמט חובה:\n"
            'שאלה: [שאלה על ההבדל בין רש"י לרמב"ן]\n'
            "תשובה: [הצג את שתי הדעות עם ציוני מקור]"
        ),
    }
    return f"--- מקורות ---\n{ctx}\n\n--- משימה ---\n{task[qtype]}"


def batch_generate(prompts: list[str]) -> list[str]:
    messages_batch = [
        [{"role": "system", "content": SYSTEM_PROMPT},
         {"role": "user",   "content": p}]
        for p in prompts
    ]
    texts = [
        tokenizer.apply_chat_template(
            m,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,   # מבטל thinking mode של Qwen3.5
        )
        for m in messages_batch
    ]
    inputs = tokenizer(
        texts, return_tensors="pt", padding=True,
        truncation=True, max_length=2048,
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
    input_len = inputs["input_ids"].shape[1]
    for out in outputs:
        decoded = tokenizer.decode(out[input_len:], skip_special_tokens=True)
        results.append(decoded.strip())
    return results


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


def count_sentences(text: str) -> int:
    parts = re.split(r'[.!?]\s+', text.strip())
    return len([p for p in parts if len(p.strip()) > 5])

def non_hebrew_ratio(text: str) -> float:
    hebrew  = sum(1 for c in text if 'א' <= c <= 'ת')
    non_heb = sum(1 for c in text if c.isalpha() and not ('א' <= c <= 'ת'))
    total   = hebrew + non_heb
    return non_heb / total if total > 0 else 0.0

def validate(q: str, a: str, qtype: str) -> tuple[bool, str]:
    if non_hebrew_ratio(a) > 0.10: return False, "תווים לא-עבריים"
    if non_hebrew_ratio(q) > 0.10: return False, "שאלה לא-עברית"
    s = count_sentences(a)
    if s < 4:  return False, f"קצר מדי ({s} משפטים)"
    if s > 15: return False, f"ארוך מדי ({s} משפטים)"
    if len(q.strip()) < 10: return False, "שאלה קצרה"
    if qtype == "rashi"  and 'רש"י' not in a and "רשי" not in a:
        return False, 'חסר רש"י'
    if qtype == "ramban" and 'רמב"ן' not in a and "רמבן" not in a:
        return False, 'חסר רמב"ן'
    if qtype == "compare":
        if ('רש"י' not in a and "רשי" not in a) or \
           ('רמב"ן' not in a and "רמבן" not in a):
            return False, "חסר אחד המפרשים"
    return True, ""

# ═══════════════════════════════════════════════════════════════════════════════
# %% [markdown]
# ## שלב 5 — לולאת ייצור
# ═══════════════════════════════════════════════════════════════════════════════

# %% [code]

generated      = 0
rejected       = 0
reject_reasons = Counter()
samples        = []   # לשמירה ולהדפסה

pbar = tqdm(total=TARGET, desc="מייצר זוגות")

while generated < TARGET:
    # בנה batch
    batch = []
    for _ in range(min(BATCH_SIZE, TARGET - generated)):
        qtype     = random.choices(QUESTION_TYPES, weights=TYPE_WEIGHTS)[0]
        verse_key = random.choice(POOLS[qtype])
        prompt    = build_user_prompt(verse_key, qtype)
        batch.append((qtype, verse_key, prompt))

    raw_outputs = batch_generate([b[2] for b in batch])

    for (qtype, verse_key, _), raw in zip(batch, raw_outputs):
        parsed = parse_qa(raw)
        if not parsed:
            rejected += 1
            reject_reasons["parse_error"] += 1
            continue

        q, a   = parsed
        ok, reason = validate(q, a, qtype)
        if not ok:
            rejected += 1
            reject_reasons[reason] += 1
            continue

        record = {
            "messages": [
                {"role": "system",    "content": SYSTEM_PROMPT},
                {"role": "user",      "content": q},
                {"role": "assistant", "content": a},
            ],
            "metadata": {"type": qtype, "verse_key": verse_key},
        }
        samples.append(record)
        generated += 1
        pbar.update(1)

pbar.close()

# שמירה
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    for s in samples:
        f.write(json.dumps(s, ensure_ascii=False) + "\n")

print(f"\n✅ נשמרו {generated} רשומות → {OUTPUT_FILE}")
print(f"❌ נפסלו: {rejected}")

# ═══════════════════════════════════════════════════════════════════════════════
# %% [markdown]
# ## שלב 6 — תצוגה לבדיקה ידנית
# ═══════════════════════════════════════════════════════════════════════════════

# %% [code]

print("\n" + "═"*60)
print("  בדיקה ידנית — 50 רשומות")
print("═"*60)

for i, s in enumerate(samples, 1):
    qtype = s["metadata"]["type"]
    vkey  = s["metadata"]["verse_key"]
    q     = s["messages"][1]["content"]
    a     = s["messages"][2]["content"]
    sents = count_sentences(a)

    print(f"\n[{i:02d}/{TARGET}] סוג: {qtype} | פסוק: {vkey} | {sents} משפטים")
    print(f"  שאלה:  {q[:120]}")
    print(f"  תשובה: {a[:200]}...")
    print("-"*50)

# ═══════════════════════════════════════════════════════════════════════════════
# %% [markdown]
# ## שלב 7 — דוח
# ═══════════════════════════════════════════════════════════════════════════════

# %% [code]

type_counts = Counter(s["metadata"]["type"] for s in samples)
avg_len     = sum(
    len(s["messages"][2]["content"]) for s in samples
) // max(len(samples), 1)

report = [
    "═"*50,
    "  Chavruta.AI v4 — דוח בדיקה (50 רשומות)",
    "═"*50,
    f"  ✅ נוצרו:    {generated}",
    f"  ❌ נפסלו:    {rejected}",
    f"  📏 ממוצע:    {avg_len} תווים לתשובה",
    "",
    "  לפי סוג:",
    *[f"    {t:10s}: {n}" for t, n in type_counts.items()],
    "",
    "  סיבות פסילה:",
    *[f"    {n}x  {r}" for r, n in reject_reasons.most_common()],
    "═"*50,
    "  >> בדוק את הפלט ידנית לפני הרצה מלאה! <<",
    "═"*50,
]

report_text = "\n".join(report)
print(report_text)
with open(REPORT_FILE, "w", encoding="utf-8") as f:
    f.write(report_text)
