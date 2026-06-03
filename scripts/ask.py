# -*- coding: utf-8 -*-
"""
ask.py — שאל את החברותא שאלה אחת (RAG מלא: אחזור + גנרציה מעוגנת).
─────────────────────────────────────────────────────────────────────────────
שימוש:
    python scripts/ask.py "According to Rashi, why is the light called good?"
    python scripts/ask.py "מה אומר רש\"י על בריאת האור?"

מודל גנרציה: לפי config.OLLAMA_MODEL (ברירת מחדל granite4.1:3b — לא-thinking).
אחזור: bge-m3 → Qdrant מקומי. דו-לשוני: עונה בשפת השאלה.
"""
import sys, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rag_pipeline import ChavrutaPipeline


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="+", help="השאלה")
    ap.add_argument("--k", type=int, default=None, help="כמה צ'אנקים לשלוף")
    ap.add_argument("--enrich", action="store_true",
                    help="העשרה חיה מ-Sefaria (אבן-עזרא, רד\"ק, ספורנו... — דורש אינטרנט)")
    args = ap.parse_args()
    q = " ".join(args.question)

    p = ChavrutaPipeline(top_k=args.k) if args.k else ChavrutaPipeline()
    print(f"\n🙋 {q}")
    res = p.ask(q, enrich=args.enrich)

    print("\n📖 SOURCES:")
    for s in res["sources"]:
        print("  ", s)
    print("\n💬 ANSWER:\n")
    print(res["response"].strip())
    print()


if __name__ == "__main__":
    main()
