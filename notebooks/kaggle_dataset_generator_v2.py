# %% [markdown]
# # Chavruta.AI — Dataset Generator v2
# מודל: google/gemma-3-4b-it | 4-bit | קריאה אחת לזוג

# %% [code] — התקנות
# !pip install transformers accelerate bitsandbytes tqdm -q

# %% [code] — ייבואים והגדרות
import json, random, torch, os, time, re
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from tqdm import tqdm

# ── הגדרות — שנה רק את השורות האלה בין notebooks ──────────────
MODEL_ID    = "google/gemma-3-4b-it"
START_FROM  = 0       # A=0 | B=1500 | C=3000 | D=4500
MAX_PAIRS   = 1500    # 1500 לכל notebook

CHUNKS_FILE     = "/kaggle/input/datasets/yehudarubin/chavruta/all_chunks.json"
OUTPUT_FILE     = f"/kaggle/working/chavruta_dataset_{START_FROM}.jsonl"
CHECKPOINT_FILE = f"/kaggle/working/checkpoint_{START_FROM}.json"

MAX_NEW_TOKENS  = 380
TEMPERATURE     = 0.7

# ── פרופורציות סוגי שאלות ──────────────────────────────────────
QUESTION_TYPES = {
    "simple":      0.30,
    "compare":     0.30,
    "deep":        0.25,
    "integrative": 0.15,
}

# %% [code] — טעינת צ'אנקים
print("טוען צ'אנקים...")
with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

chunks = data["chunks"]
print(f"נטענו {len(chunks):,} צ'אנקים")

# אינדקס לפי ספר+פרק+פסוק
verse_index = {}
for c in chunks:
    key = f"{c['metadata']['book']}.{c['metadata']['chapter']}.{c['metadata']['verse']}"
    if key not in verse_index:
        verse_index[key] = {}
    verse_index[key][c['metadata']['chunk_type']] = c

# פסוקים עם גם רש"י וגם רמב"ן
compare_verses = [
    k for k, v in verse_index.items()
    if "rashi" in v and "ramban" in v
]
print(f"פסוקים עם רש\"י + רמב\"ן: {len(compare_verses):,}")

# %% [code] — טעינת מודל עם 4-bit
print(f"טוען מודל: {MODEL_ID}")

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16,
)

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    quantization_config=bnb_config,
    device_map="auto",
)
model.eval()
print("מודל נטען ✅")

# %% [code] — פונקציות עזר

SYSTEM_PROMPT = """אתה חברותא — עוזר לימוד תורה מלומד.
תפקידך לייצר שאלות ותשובות איכותיות מהמקורות.
ענה תמיד בעברית בלבד. היה מדויק ותציין מקורות."""

def generate(prompt: str, max_tokens: int = MAX_NEW_TOKENS) -> str:
    messages = [
        {"role": "user", "content": prompt}
    ]
    text = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer(text, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            temperature=TEMPERATURE,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id,
        )
    response = tokenizer.decode(
        outputs[0][inputs["input_ids"].shape[1]:],
        skip_special_tokens=True,
    )
    return response.strip()


def get_context(chunks_list: list, max_chars: int = 1200) -> str:
    parts, total = [], 0
    for c in chunks_list:
        book  = c["metadata"]["book"]
        ch    = c["metadata"]["chapter"]
        vs    = c["metadata"]["verse"]
        ct    = c["metadata"]["chunk_type"]
        label = {"chumash": "חומש", "rashi": 'רש"י', "ramban": 'רמב"ן'}.get(ct, ct)
        block = f"[{label}] {book} {ch}:{vs}\n{c['document'][:280]}"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts)


def parse_qa(text: str) -> tuple[str, str] | None:
    """מחלץ שאלה ותשובה מהפלט."""
    # ניסיון 1 — פורמט מסומן
    if "שאלה:" in text and "תשובה:" in text:
        try:
            q_part = text.split("שאלה:", 1)[1].split("תשובה:", 1)[0].strip()
            a_part = text.split("תשובה:", 1)[1].strip()
            if len(q_part) > 10 and len(a_part) > 20:
                return q_part, a_part
        except Exception:
            pass

    # ניסיון 2 — שורה ראשונה = שאלה, שאר = תשובה
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    if len(lines) >= 2:
        question = lines[0].lstrip("?-•").strip()
        answer   = " ".join(lines[1:])
        if len(question) > 10 and len(answer) > 20:
            return question, answer

    return None


# %% [code] — מחוללי זוגות (קריאה אחת לכל זוג)

def make_simple_pair(chunk: dict) -> dict | None:
    book  = chunk["metadata"]["book"]
    ch    = chunk["metadata"]["chapter"]
    vs    = chunk["metadata"]["verse"]
    ct    = chunk["metadata"]["chunk_type"]
    label = {"chumash": "החומש", "rashi": 'רש"י', "ramban": 'רמב"ן'}.get(ct, ct)

    key   = f"{book}.{ch}.{vs}"
    ctx   = get_context(list(verse_index.get(key, {}).values()))

    prompt = f"""{SYSTEM_PROMPT}

מקורות:
{ctx}

צור שאלה ותשובה על {label} בפסוק {book} {ch}:{vs}.

פורמט חובה:
שאלה: [שאלה אחת ברורה]
תשובה: [תשובה מבוססת מקורות עם ציון פסוק]"""

    result = generate(prompt)
    parsed = parse_qa(result)
    if not parsed:
        return None
    q, a = parsed
    return {"type": "simple", "book": book, "chapter": ch, "verse": vs,
            "prompt": q, "completion": a}


def make_compare_pair(verse_key: str) -> dict | None:
    verse = verse_index[verse_key]
    book  = verse["rashi"]["metadata"]["book"]
    ch    = verse["rashi"]["metadata"]["chapter"]
    vs    = verse["rashi"]["metadata"]["verse"]
    ctx   = get_context(list(verse.values()))

    prompt = f"""{SYSTEM_PROMPT}

מקורות:
{ctx}

צור שאלת השוואה בין רש"י לרמב"ן על {book} {ch}:{vs}.

פורמט חובה:
שאלה: [שאלה על ההבדל בין רש"י לרמב"ן]
תשובה: [הצג את שתי הדעות עם ציוני מקור]"""

    result = generate(prompt)
    parsed = parse_qa(result)
    if not parsed:
        return None
    q, a = parsed
    return {"type": "compare", "book": book, "chapter": ch, "verse": vs,
            "prompt": q, "completion": a}


def make_deep_pair(chunk: dict) -> dict | None:
    book  = chunk["metadata"]["book"]
    ch    = chunk["metadata"]["chapter"]
    vs    = chunk["metadata"]["verse"]
    ct    = chunk["metadata"]["chunk_type"]
    label = {"chumash": "החומש", "rashi": 'רש"י', "ramban": 'רמב"ן'}.get(ct, ct)

    key = f"{book}.{ch}.{vs}"
    ctx = get_context(list(verse_index.get(key, {}).values()))

    prompt = f"""{SYSTEM_PROMPT}

מקורות:
{ctx}

צור שאלה מעמיקה על מושג או טעם ב{label} על {book} {ch}:{vs}.

פורמט חובה:
שאלה: [שאלה מעמיקה על משמעות או טעם]
תשובה: [תשובה מפורטת עם ציוני מקור]"""

    result = generate(prompt)
    parsed = parse_qa(result)
    if not parsed:
        return None
    q, a = parsed
    return {"type": "deep", "book": book, "chapter": ch, "verse": vs,
            "prompt": q, "completion": a}


def make_integrative_pair() -> dict | None:
    sample = random.sample(chunks, 3)
    ctx    = get_context(sample)

    prompt = f"""{SYSTEM_PROMPT}

מקורות:
{ctx}

צור שאלה אינטגרטיבית שמשלבת כמה מהמקורות האלה.

פורמט חובה:
שאלה: [שאלה שמחברת בין הפסוקים]
תשובה: [תשובה שמשלבת את המקורות עם ציונים]"""

    result = generate(prompt)
    parsed = parse_qa(result)
    if not parsed:
        return None
    q, a = parsed
    return {"type": "integrative", "prompt": q, "completion": a}


# %% [code] — לולאת ייצור ראשית

def load_checkpoint() -> int:
    if Path(CHECKPOINT_FILE).exists():
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)["count"]
    return START_FROM

def save_checkpoint(count: int):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump({"count": count}, f)

def pick_type() -> str:
    r = random.random()
    if r < 0.30: return "simple"
    if r < 0.60: return "compare"
    if r < 0.85: return "deep"
    return "integrative"


start_count = load_checkpoint()
target      = START_FROM + MAX_PAIRS
print(f"מתחיל מ-{start_count} | יעד: {target}")

output = open(OUTPUT_FILE, "a", encoding="utf-8")
count  = start_count
errors = 0

pbar = tqdm(total=target, initial=start_count, desc="מייצר זוגות")

while count < target:
    try:
        qtype = pick_type()
        pair  = None

        if qtype == "simple":
            pair = make_simple_pair(random.choice(chunks))
        elif qtype == "compare" and compare_verses:
            pair = make_compare_pair(random.choice(compare_verses))
        elif qtype == "deep":
            pair = make_deep_pair(random.choice(chunks))
        else:
            pair = make_integrative_pair()

        if pair:
            output.write(json.dumps(pair, ensure_ascii=False) + "\n")
            output.flush()
            count += 1
            errors = 0
            pbar.update(1)
            pbar.set_postfix({"סוג": qtype, "שגיאות": errors})
            save_checkpoint(count)
        else:
            errors += 1
            if errors > 15:
                print("יותר מדי שגיאות — עוצר")
                break

    except KeyboardInterrupt:
        print("\nעצר על ידי המשתמש")
        break
    except Exception as e:
        errors += 1
        print(f"\nשגיאה ({errors}): {e}")
        time.sleep(2)

output.close()
pbar.close()
print(f"\n✅ סיום — {count} זוגות נשמרו ב-{OUTPUT_FILE}")

# %% [code] — סטטיסטיקות סיום
from collections import Counter

pairs = []
with open(OUTPUT_FILE, encoding="utf-8") as f:
    for line in f:
        pairs.append(json.loads(line))

types = Counter(p["type"] for p in pairs)
print(f"\nסה\"כ זוגות: {len(pairs):,}")
for t, n in types.items():
    pct = n / len(pairs) * 100
    print(f"  {t}: {n} ({pct:.1f}%)")

print("\nדוגמה ראשונה:")
if pairs:
    print(f"  שאלה:  {pairs[0]['prompt'][:100]}")
    print(f"  תשובה: {pairs[0]['completion'][:150]}")
