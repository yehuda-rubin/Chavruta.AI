import json

with open("data/raw/bereishit.json", encoding="utf-8") as f:
    data = json.load(f)

verses = data["verses"]

# הדפסת 5 פסוקים ראשונים
print("=== 5 פסוקים ראשונים ===")
for v in verses[:5]:
    print(f"\n--- {v['verse_id']} ---")
    print(f"  text_en:   {v['text_en'][:80]}")
    print(f"  rashi_en:  '{v['rashi']['text_en'][:80]}'")
    print(f"  rashi_he:  '{v['rashi']['text_he'][:80]}'")
    print(f"  has_rashi: {v['rashi']['has_content']}")

# ספירת פסוקים עם תוכן אמיתי
has_rashi  = sum(1 for v in verses if v["rashi"]["has_content"])
has_ramban = sum(1 for v in verses if v["ramban"]["has_content"])

print(f"\n=== סיכום ===")
print(f"סה\"כ פסוקים:  {len(verses)}")
print(f"יש רש\"י:      {has_rashi} ({100*has_rashi/len(verses):.1f}%)")
print(f"יש רמב\"ן:     {has_ramban} ({100*has_ramban/len(verses):.1f}%)")

# בדיקה: מה מכיל פסוק שנרשם כ"חסר רש"י"
missing = [v for v in verses if not v["rashi"]["has_content"]]
if missing:
    print(f"\nדוגמה לפסוק ללא רש\"י: {missing[0]['verse_id']}")
    print(f"  text_en: {missing[0]['text_en'][:80]}")
