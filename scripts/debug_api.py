"""בדיקת מבנה ה-API של Sefaria לפרק ספציפי."""
import json
from pathlib import Path

cache_dir = Path("data/raw/cache")

# בדיקת מבנה רש"י על בראשית פרק א
rashi_ch1_file = cache_dir / "Rashi_on_Bereishit.1.json"
torah_ch1_file = cache_dir / "Bereishit.1.json"

print("=== Torah Bereishit.1 ===")
if torah_ch1_file.exists():
    data = json.loads(torah_ch1_file.read_text(encoding="utf-8"))
    text = data.get("text", [])
    he   = data.get("he", [])
    print(f"type(text):       {type(text)}")
    print(f"len(text):        {len(text)}")
    print(f"text[0][:60]:     {str(text[0])[:60]}")
    print(f"text[3][:60]:     {str(text[3])[:60]}")  # verse 4

print()
print("=== Rashi on Bereishit.1 ===")
if rashi_ch1_file.exists():
    data = json.loads(rashi_ch1_file.read_text(encoding="utf-8"))
    text = data.get("text", [])
    he   = data.get("he", [])
    print(f"type(text):       {type(text)}")
    print(f"len(text):        {len(text)}")
    for i, entry in enumerate(text[:8]):
        print(f"  text[{i}] (v.{i+1}): type={type(entry).__name__}  val={str(entry)[:80]}")
else:
    print("קובץ לא נמצא")
    # רשימת קבצי cache קיימים
    files = list(cache_dir.glob("Rashi_on_Bereishit*.json"))
    print(f"קבצי Rashi בcache: {[f.name for f in files[:10]]}")
