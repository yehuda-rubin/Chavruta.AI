# %% [markdown]
# # Chavruta.AI — Dataset Generator
# מייצר זוגות שאלה-תשובה מה-DB של תורה/רש"י/רמבן
# הרץ על Kaggle עם GPU T4 x2

# %% [code] — התקנות
# !pip install transformers accelerate bitsandbytes tqdm -q

# %% [code] — ייבואים והגדרות
import json, random, torch, os, time
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM
from tqdm import tqdm

# ── הגדרות ──────────────────────────────────────────────────────
MODEL_ID        = "Qwen/Qwen2.5-3B-Instruct"   # חינמי, מהיר, עברית טובה
CHUNKS_FILE     = "/kaggle/input/chavruta/all_chunks.json"
OUTPUT_FILE     = "/kaggle/working/chavruta_dataset.jsonl"
CHECKPOINT_FILE = "/kaggle/working/checkpoint.json"
MAX_NEW_TOKENS  = 512
TEMPERATURE     = 0.7
MAX_PAIRS       = 6000   # יעד — שנה לפי הצורך

# פרופורציות סוגי שאלות
QUESTION_TYPES = {
    "simple":      0.30,   # "מה אומר רש"י על..."
    "compare":     0.30,   # "במה נחלקים רש"י ורמב"ן..."
    "deep":        0.25,   # "מה הסיבה לפי רמב"ן ש..."
    "integrative": 0.15,   # "איך מסביר רש"י את הסתירה בין..."
}

# %% [code] — טעינת צ'אנקים
print("טוען צ'אנקים...")
with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

chunks = data["chunks"]
print(f"נטענו {len(chunks):,} צ'אנקים")

# אינדקס לפי ספר+פרק+פסוק לצורך שאלות השוואה
verse_index = {}
for c in chunks:
    key = f"{c['metadata']['book']}.{c['metadata']['chapter']}.{c['metadata']['verse']}"
    if key not in verse_index:
        verse_index[key] = {}
    verse_index[key][c['metadata']['chunk_type']] = c

# פסוקים שיש להם גם רש"י וגם רמב"ן (לשאלות השוואה)
compare_verses = [
    k for k, v in verse_index.items()
    if "rashi" in v and "ramban" in v
]
print(f"פסוקים עם רש\"י + רמב\"ן: {len(compare_verses):,}")

# %% [code] — טעינת מודל
print(f"טוען מודל: {MODEL_ID}")
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.float16,
    device_map="auto",
)
model.eval()
print("מודל נטען ✅")

# %% [code] — פונקציות עזר

def generate(prompt: str, system: str = "") -> str:
    """מייצר טקסט מהמודל."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    text = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer(text, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            temperature=TEMPERATURE,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id,
        )
    response = tokenizer.decode(
        outputs[0][inputs["input_ids"].shape[1]:],
        skip_special_tokens=True
    )
    return response.strip()


def get_context(chunks_list: list, max_chars: int = 1500) -> str:
    """מרכיב הקשר מרשימת צ'אנקים."""
    parts = []
    total = 0
    for c in chunks_list:
        book = c["metadata"]["book"]
        ch   = c["metadata"]["chapter"]
        vs   = c["metadata"]["verse"]
        ct   = c["metadata"]["chunk_type"]
        label = {"chumash": "חומש", "rashi": 'רש"י', "ramban": 'רמב"ן'}.get(ct, ct)
        block = f"[{label}] {book} {ch}:{vs}\n{c['document'][:300]}"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts)


# %% [code] — מחוללי שאלות לפי סוג

SYSTEM_GENERATOR = """אתה עוזר ליצירת dataset לאימון מודל תורה.
צור שאלה אחת בלבד בעברית — קצרה וברורה.
אל תוסיף הסבר, רק את השאלה עצמה."""

SYSTEM_ANSWERER = """אתה חברותא — עוזר לימוד תורה מלומד.
ענה בעברית בהתבסס על המקורות בלבד.
ציין ספר פרק ופסוק בכל טענה.
אם המקורות לא מכסים את השאלה — אמור זאת."""


def make_simple_pair(chunk: dict) -> dict | None:
    """שאלה פשוטה על פסוק ספציפי."""
    book = chunk["metadata"]["book"]
    ch   = chunk["metadata"]["chapter"]
    vs   = chunk["metadata"]["verse"]
    ct   = chunk["metadata"]["chunk_type"]
    label = {"chumash": "החומש", "rashi": 'רש"י', "ramban": 'רמב"ן'}.get(ct, ct)

    prompt = f"""הטקסט הבא הוא מ{label} על {book} {ch}:{vs}:

{chunk['document'][:400]}

צור שאלה אחת בסגנון: "מה אומר {label} על..." או "כיצד מפרש {label} את..."."""

    question = generate(prompt, SYSTEM_GENERATOR)
    if not question or len(question) < 10:
        return None

    # הקשר לתשובה
    key = f"{book}.{ch}.{vs}"
    context_chunks = list(verse_index.get(key, {}).values())
    context = get_context(context_chunks)

    answer_prompt = f"""מקורות:
{context}

שאלה: {question}"""

    answer = generate(answer_prompt, SYSTEM_ANSWERER)
    if not answer or len(answer) < 20:
        return None

    return {
        "type": "simple",
        "book": book, "chapter": ch, "verse": vs,
        "prompt": question,
        "completion": answer,
    }


def make_compare_pair(verse_key: str) -> dict | None:
    """שאלת השוואה בין רש"י לרמב"ן."""
    verse = verse_index[verse_key]
    book  = verse["rashi"]["metadata"]["book"]
    ch    = verse["rashi"]["metadata"]["chapter"]
    vs    = verse["rashi"]["metadata"]["verse"]

    rashi_text  = verse["rashi"]["document"][:300]
    ramban_text = verse["ramban"]["document"][:300]

    prompt = f"""להלן פירושי רש"י ורמב"ן על {book} {ch}:{vs}:

רש"י: {rashi_text}
רמב"ן: {ramban_text}

צור שאלה אחת בסגנון: "במה נחלקים רש\"י ורמב\"ן על..." או "מה ההבדל בין פירוש רש\"י לרמב\"ן..."."""

    question = generate(prompt, SYSTEM_GENERATOR)
    if not question or len(question) < 10:
        return None

    context_chunks = list(verse.values())
    context = get_context(context_chunks)

    answer_prompt = f"""מקורות:
{context}

שאלה: {question}"""

    answer = generate(answer_prompt, SYSTEM_ANSWERER)
    if not answer or len(answer) < 20:
        return None

    return {
        "type": "compare",
        "book": book, "chapter": ch, "verse": vs,
        "prompt": question,
        "completion": answer,
    }


def make_deep_pair(chunk: dict) -> dict | None:
    """שאלה מושגית/מעמיקה."""
    book = chunk["metadata"]["book"]
    ch   = chunk["metadata"]["chapter"]
    vs   = chunk["metadata"]["verse"]
    ct   = chunk["metadata"]["chunk_type"]
    label = {"chumash": "החומש", "rashi": 'רש"י', "ramban": 'רמב"ן'}.get(ct, ct)

    prompt = f"""הטקסט הבא הוא מ{label} על {book} {ch}:{vs}:

{chunk['document'][:400]}

צור שאלה מעמיקה אחת על מושג, טעם, או משמעות רוחנית בסגנון:
"מה הסיבה לפי {label} ש..." או "מה המשמעות של..." או "מדוע..."."""

    question = generate(prompt, SYSTEM_GENERATOR)
    if not question or len(question) < 10:
        return None

    key = f"{book}.{ch}.{vs}"
    context_chunks = list(verse_index.get(key, {}).values())
    context = get_context(context_chunks)

    answer_prompt = f"""מקורות:
{context}

שאלה: {question}"""

    answer = generate(answer_prompt, SYSTEM_ANSWERER)
    if not answer or len(answer) < 20:
        return None

    return {
        "type": "deep",
        "book": book, "chapter": ch, "verse": vs,
        "prompt": question,
        "completion": answer,
    }


def make_integrative_pair() -> dict | None:
    """שאלה אינטגרטיבית — כמה פסוקים."""
    # בחר 2-3 צ'אנקים מאותו ספר
    sample = random.sample(chunks, 3)
    book = sample[0]["metadata"]["book"]

    texts = "\n\n".join([
        f"[{c['metadata']['chunk_type']}] {c['metadata']['book']} "
        f"{c['metadata']['chapter']}:{c['metadata']['verse']}\n{c['document'][:250]}"
        for c in sample
    ])

    prompt = f"""להלן מספר מקורות מהתורה:

{texts}

צור שאלה אינטגרטיבית אחת שמשלבת כמה מהמקורות האלה, בסגנון:
"איך מסביר רש\"י..." או "מה הקשר בין..." או "כיצד מתיישבת הסתירה..."."""

    question = generate(prompt, SYSTEM_GENERATOR)
    if not question or len(question) < 10:
        return None

    context = get_context(sample)
    answer_prompt = f"""מקורות:
{context}

שאלה: {question}"""

    answer = generate(answer_prompt, SYSTEM_ANSWERER)
    if not answer or len(answer) < 20:
        return None

    return {
        "type": "integrative",
        "prompt": question,
        "completion": answer,
    }


# %% [code] — לולאת ייצור ראשית

def load_checkpoint() -> int:
    if Path(CHECKPOINT_FILE).exists():
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)["count"]
    return 0

def save_checkpoint(count: int):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump({"count": count}, f)

def pick_type() -> str:
    r = random.random()
    if r < 0.30:   return "simple"
    if r < 0.60:   return "compare"
    if r < 0.85:   return "deep"
    return "integrative"


start_count = load_checkpoint()
print(f"מתחיל מ-{start_count} זוגות קיימים")

output = open(OUTPUT_FILE, "a", encoding="utf-8")
count  = start_count
errors = 0

pbar = tqdm(total=MAX_PAIRS, initial=start_count, desc="מייצר זוגות")

while count < MAX_PAIRS:
    try:
        qtype = pick_type()
        pair  = None

        if qtype == "simple":
            chunk = random.choice(chunks)
            pair  = make_simple_pair(chunk)

        elif qtype == "compare" and compare_verses:
            verse_key = random.choice(compare_verses)
            pair = make_compare_pair(verse_key)

        elif qtype == "deep":
            chunk = random.choice(chunks)
            pair  = make_deep_pair(chunk)

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

    except KeyboardInterrupt:
        print("\nעצר על ידי המשתמש")
        break
    except Exception as e:
        errors += 1
        print(f"\nשגיאה ({errors}): {e}")
        if errors > 10:
            print("יותר מדי שגיאות — עוצר")
            break
        time.sleep(2)

output.close()
pbar.close()
print(f"\n✅ סיום — {count} זוגות נשמרו ב-{OUTPUT_FILE}")

# %% [code] — סטטיסטיקות
pairs = []
with open(OUTPUT_FILE, encoding="utf-8") as f:
    for line in f:
        pairs.append(json.loads(line))

from collections import Counter
types = Counter(p["type"] for p in pairs)
print(f"\nסה\"כ זוגות: {len(pairs):,}")
print("לפי סוג:")
for t, n in types.items():
    print(f"  {t}: {n} ({n/len(pairs)*100:.1f}%)")
