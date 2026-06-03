# -*- coding: utf-8 -*-
"""
upload_dataset_hf.py — מעלה את קבצי האימון (+ סקריפט האימון) ל-Hugging Face Hub.
─────────────────────────────────────────────────────────────────────────────
למה: torah_mixed_train.jsonl הוא 162MB — מעל מגבלת 100MB של GitHub. HF Hub חינמי,
ללא מגבלת גודל, ומהיר מאוד למשיכה ב-Colab. הפרדה נקייה: קוד→GitHub, דאטה→HF.

הרצה (פעם אחת מהמחשב שלך):
    pip install -U huggingface_hub
    # התחבר פעם אחת:  huggingface-cli login    (או הגדר HF_TOKEN)
    python scripts/upload_dataset_hf.py --repo <user>/chavruta-torah-mixed

כל פעם שתגדיל את הדאטה (עוד מפרשים / שאר התנ"ך) — הרץ שוב כדי לעדכן את ה-Hub.
"""

import argparse
import os
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True,
                    help="dataset repo id, e.g. yourname/chavruta-torah-mixed")
    ap.add_argument("--token", default=os.environ.get("HF_TOKEN"),
                    help="HF token (או דרך huggingface-cli login / משתנה HF_TOKEN)")
    ap.add_argument("--private", action="store_true", help="צור repo פרטי")
    ap.add_argument("--with_source", action="store_true",
                    help="העלה גם את all_chunks.json (107MB) כדי לאפשר רגנרציה")
    ap.add_argument("--full", action="store_true",
                    help="העלה רק את all_chunks_full.json (הקורפוס המלא — תנ\"ך + מפרשים)")
    args = ap.parse_args()

    from huggingface_hub import HfApi, create_repo

    # הקבצים שמהם המחברת תמשוך
    if args.full:
        files = [("data/processed/all_chunks_full.json", "all_chunks_full.json")]
    else:
        files = [
            ("data/processed/torah_mixed_train.jsonl", "torah_mixed_train.jsonl"),
            ("data/processed/torah_mixed_val.jsonl",   "torah_mixed_val.jsonl"),
            ("scripts/train_lora.py",                  "train_lora.py"),
        ]
        if args.with_source:
            files.append(("data/processed/all_chunks.json", "all_chunks.json"))

    missing = [src for src, _ in files if not Path(src).exists()]
    if missing:
        print("❌ חסרים קבצים:", *missing, sep="\n  ")
        return

    print(f"📦 creating dataset repo: {args.repo} (private={args.private})")
    create_repo(args.repo, repo_type="dataset", exist_ok=True,
                private=args.private, token=args.token)

    api = HfApi()
    for src, dst in files:
        mb = Path(src).stat().st_size / 1e6
        print(f"⬆️  {mb:7.2f} MB  {src}  →  {dst}")
        api.upload_file(
            path_or_fileobj=src,
            path_in_repo=dst,
            repo_id=args.repo,
            repo_type="dataset",
            token=args.token,
        )

    print(f"\n✅ done → https://huggingface.co/datasets/{args.repo}")
    print(f"   במחברת הגדר:  HF_DATASET = \"{args.repo}\"")


if __name__ == "__main__":
    main()
