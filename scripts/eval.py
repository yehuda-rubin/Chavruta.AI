# -*- coding: utf-8 -*-
"""
eval.py — סט שאלות הערכה (benchmark) לאיכות האחזור/התשובה של Chavruta.AI.
─────────────────────────────────────────────────────────────────────────────
מכסה: חיפוש פסוק, מפרש ספציפי (סינון), השוואה, מושגי, נ"ך/כתובים, תרגום — בשתי השפות.
מריצים אחרי שהקורפוס המלא נטען ל-Qdrant.

שימוש:
    python scripts/eval.py                # אחזור בלבד (מהיר) — מדפיס מקורות
    python scripts/eval.py --generate     # גם מייצר תשובות (איטי)
    python scripts/eval.py --enrich       # + העשרה חיה מ-Sefaria
"""
import sys, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# (שאלה, תגית-ממד) — תגית מציינת מה נבדק ומה מצופה לחזור
QUESTIONS = [
    ("What does the verse Genesis 1:1 say?",                         "pasuk/en"),
    ("מה כתוב בפסוק הראשון של תהילים כג?",                            "pasuk/he"),
    ("What does Rashi explain about the binding of Isaac?",          "commentator:Rashi/en"),
    ("מה אומר אבן עזרא על בריאת העולם?",                              "commentator:IbnEzra/he"),
    ("What does Radak say about the prophet Jonah?",                 "commentator:Radak/en"),
    ('מה מפרש המלבי"ם על נבואת ישעיהו?',                              "commentator:Malbim/he"),
    ('מה אומרות המצודות על מזמור בתהילים?',                           "commentator:Metzudot/he"),
    ("What is the difference between Rashi and Ramban on creation?", "compare/en"),
    ('השווה בין רש"י לאבן עזרא על יציאת מצרים',                       "compare/he"),
    ("What does the Torah teach about Shabbat?",                     "concept/en"),
    ("מהי המשמעות של עשרת הדיברות?",                                  "concept/he"),
    ("What is the significance of the Akeidah?",                     "concept/en"),
    ("What is the central message of the book of Jonah?",            "neviim/en"),
    ("מה המסר של מגילת רות?",                                         "ketuvim/he"),
    ("What does Isaiah prophesy about peace among nations?",         "neviim/en"),
    ("מה אומר תרגום אונקלוס על תחילת בראשית?",                        "targum:Onkelos/he"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--generate", action="store_true", help="גם ייצר תשובות (איטי)")
    ap.add_argument("--enrich", action="store_true", help="העשרה חיה מ-Sefaria")
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()

    from rag_pipeline import ChavrutaPipeline
    p = ChavrutaPipeline(top_k=args.k)

    for i, (q, tag) in enumerate(QUESTIONS, 1):
        print("\n" + "=" * 70)
        print(f"[{i:02}/{len(QUESTIONS)}] ({tag})\n🙋 {q}")
        if args.generate:
            res = p.ask(q, enrich=args.enrich)
            print("\n📖 sources:")
            for s in res["sources"]:
                print("   ", s)
            print("\n💬 answer:\n" + res["response"].strip()[:600])
        else:
            chunks = p.retrieve(q, enrich=args.enrich)
            print("📖 retrieved:")
            for c in chunks[:args.k + 2]:
                m = c["meta"]
                cmt = m.get("commentator", "") or m.get("chunk_type", "")
                print(f"   {c['similarity']:.3f}  {cmt:16} {m.get('book')} "
                      f"{m.get('chapter')}:{m.get('verse')}")
    print("\n" + "=" * 70)
    print(f"✅ {len(QUESTIONS)} שאלות. (להרצה אחרי טעינת הקורפוס המלא ל-Qdrant)")


if __name__ == "__main__":
    main()
