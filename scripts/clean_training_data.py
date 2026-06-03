import json
import re
from pathlib import Path

def clean_translation(text: str) -> str:
    """מסיר הערות שוליים של ספריא מהתרגום"""
    # הסרת תבניות כמו "d daughters Presumed..." או "c the following A number..."
    text = re.sub(r'\b[a-z]\s+[a-z]+\s+[A-Z][^.]*\.', '', text)
    # הסרת אותיות בודדות שנשארו
    text = re.sub(r'\s+[a-z]\s+', ' ', text)
    # ניקוי רווחים כפולים
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def fix_compare_ending(text: str) -> str:
    """מסיר את המשפט הגנרי מסוף השוואות"""
    generic = "רש\"י נוטה לפשט הפסוק, בעוד הרמב\"ן מרחיב לעיתים לממד הפילוסופי והמסורתי."
    return text.replace("\n" + generic, "").replace(generic, "").strip()

def clean_jsonl(input_path: str, output_path: str):
    cleaned = []
    skipped = 0

    with open(input_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        try:
            pair = json.loads(line.strip())
            messages = pair["messages"]

            # תיקון תשובת assistant
            assistant_msg = messages[2]
            content = assistant_msg["content"]

            # תיקון 1: הסרת משפט גנרי
            content = fix_compare_ending(content)

            # תיקון 2: ניקוי הערות שוליים בתרגום
            if "תרגום:" in content:
                parts = content.split("תרגום:")
                parts[1] = clean_translation(parts[1])
                content = "תרגום:".join(parts)

            # תיקון 3: דלג על תשובות ריקות
            if len(content.strip()) < 10:
                skipped += 1
                continue

            assistant_msg["content"] = content
            cleaned.append(pair)

        except Exception:
            skipped += 1
            continue

    with open(output_path, "w", encoding="utf-8") as f:
        for pair in cleaned:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    print(f"✅ לפני ניקוי: {len(lines):,}")
    print(f"✅ אחרי ניקוי: {len(cleaned):,}")
    print(f"⚠️  דולגו: {skipped:,}")

if __name__ == "__main__":
    BASE = Path(__file__).parent.parent
    processed = BASE / "data" / "processed"

    input_path  = str(processed / "torah_training.jsonl")
    output_path = str(processed / "torah_training_clean.jsonl")

    print(f"📖 מנקה: {input_path}")
    clean_jsonl(input_path, output_path)
    print(f"📁 נשמר ל: {output_path}")
