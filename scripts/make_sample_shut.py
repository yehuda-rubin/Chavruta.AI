# -*- coding: utf-8 -*-
"""Run the 3 example שו"ת questions live (intent=halacha) and save the teshuvot.

    python scripts/make_sample_shut.py        # backend must be up on :8080

Output → sample_lessons/<id>_answer.md  and  <id>_answer.json
Reuses the Markdown formatting from make_sample_lessons.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_sample_lessons import OUT, to_md  # noqa: E402

API = "http://localhost:8080/query"

QUESTIONS = [
    ("shut_pesak",     "מבקש הוראה למעשה: כיצד עליי לנהוג בברכת הגומל לאחר טיסה ארוכה?"),
    ("shut_tzdadim",   "יש בזה צד היתר וצד איסור — האם מותר לסחוט לימון לתוך תה בשבת? מה סברות המתירים ומה סברות האוסרים?"),
    ("shut_birur_din", "מהו גדרו של 'דבר שאינו מתכוון' בהלכות שבת, ומה מקורו?"),
]


def ask(question, retries=3):
    body = json.dumps({"question": question, "intent": "halacha", "lang": "he"}).encode("utf-8")
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=1500) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            print(f"  retry ({type(e).__name__}) …", flush=True)
            time.sleep(8 * (attempt + 1))
    raise last


def main():
    index = ["# תשובות שו\"ת לדוגמה (חיות) — אחת לכל תבנית", ""]
    for tid, q in QUESTIONS:
        print(f"[{tid}] {q[:50]}… …", flush=True)
        try:
            d = ask(q)
        except Exception as e:
            print(f"  FAILED: {e}", flush=True)
            continue
        (OUT / f"{tid}_answer.json").write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / f"{tid}_answer.md").write_text(to_md(tid, q, d), encoding="utf-8")
        lp = d.get("lesson_plan") or {}
        print(f"  -> template={lp.get('template_id')} sections={len(lp.get('sections') or [])} "
              f"grounded={d.get('grounded')} chars={len(d.get('answer') or '')}", flush=True)
        index.append(f"- [{q[:60]}]({tid}_answer.md) — תבנית `{lp.get('template_id')}`, "
                     f"{len(lp.get('sections') or [])} מקטעים")
    (OUT / "shut_answers_README.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    print("\n✅ saved to sample_lessons/", flush=True)


if __name__ == "__main__":
    main()
