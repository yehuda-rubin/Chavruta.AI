# -*- coding: utf-8 -*-
"""
upload_categories.py — מעלה ל-HF את כל ה-parts של הקטגוריות החדשות, **במקביל** למשיכה.
──────────────────────────────────────────────────────────────────────────────
סורק data/processed/<slug>/<slug>_partNN.jsonl, מעלה ל-repo בשם הקובץ (root, prefix
זהה לדפוס ה-halacha → ה-Nebius embed job מוצא לפי CORPUS_PREFIX=<slug>_part), ומדלג
על מה שכבר הועלה (לפי upload-log). אפשר להריץ שוב ושוב — אידמפוטנטי.

מצב --watch: לולאה שמעלה parts חדשים כל 60 שניות עד ש-fetch מסיים (סנטינל בלוג) וכל
ה-parts הועלו — מתאים להרצה במקביל ל-fetch_category.

הרצה:
    python scripts/upload_categories.py                 # סבב יחיד (מה שמוכן עכשיו)
    python scripts/upload_categories.py --watch         # רץ עד שהכל הועלה
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

CATEGORIES = ["reference", "musar", "second_temple", "liturgy", "kabbalah",
              "chasidut", "midrash", "jewish_thought", "tosefta"]
PROCESSED = Path("data/processed")
FETCH_LOG = PROCESSED / "fetch_all_categories.log"
FETCH_SENTINEL = "ALL CATEGORIES DONE"
UPLOAD_LOG = PROCESSED / "hf_upload_categories.log"   # שורה לכל קובץ שהועלה
MIN_AGE_SEC = 15                                       # דלג על קבצים שעדיין נכתבים


def _uploaded() -> set[str]:
    if not UPLOAD_LOG.exists():
        return set()
    return {ln.strip() for ln in UPLOAD_LOG.read_text(encoding="utf-8").splitlines() if ln.strip()}


def _ready_parts(now: float) -> list[Path]:
    parts: list[Path] = []
    for slug in CATEGORIES:
        d = PROCESSED / slug
        if not d.exists():
            continue
        for p in sorted(d.glob(f"{slug}_part*.jsonl")):
            if now - p.stat().st_mtime >= MIN_AGE_SEC:   # נכתב במלואו
                parts.append(p)
    return parts


def _fetch_done() -> bool:
    return FETCH_LOG.exists() and FETCH_SENTINEL in FETCH_LOG.read_text(encoding="utf-8")


def _sweep(api, repo: str, token, now: float) -> int:
    done = _uploaded()
    pending = [p for p in _ready_parts(now) if p.name not in done]
    if not pending:
        return 0
    for p in pending:
        mb = p.stat().st_size / 1e6
        print(f"⬆️  {mb:7.2f} MB  {p}  →  {p.name}", flush=True)
        api.upload_file(path_or_fileobj=str(p), path_in_repo=p.name,
                        repo_id=repo, repo_type="dataset", token=token)
        with UPLOAD_LOG.open("a", encoding="utf-8") as f:
            f.write(p.name + "\n")
    return len(pending)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="Yehuda-Rubin/chavruta-torah-mixed")
    ap.add_argument("--token", default=None, help="HF token (ברירת מחדל: התחברות מקומית)")
    ap.add_argument("--watch", action="store_true", help="לולאה עד ש-fetch מסיים והכל הועלה")
    ap.add_argument("--interval", type=int, default=60)
    args = ap.parse_args()

    from huggingface_hub import HfApi, create_repo
    create_repo(args.repo, repo_type="dataset", exist_ok=True, token=args.token)
    api = HfApi()

    # זמן "עכשיו" בלי Date.now בתוך workflow — כאן זה סקריפט רגיל, time.time מותר.
    n = _sweep(api, args.repo, args.token, time.time())
    print(f"✓ סבב ראשון: {n} parts הועלו (סה\"כ הועלו: {len(_uploaded())})", flush=True)

    if args.watch:
        while True:
            if _fetch_done():
                # סבב אחרון לאחר שה-fetch סיים — לתפוס parts שנכתבו ממש לאחרונה
                time.sleep(MIN_AGE_SEC + 1)
                extra = _sweep(api, args.repo, args.token, time.time())
                print(f"🏁 fetch הסתיים — סבב אחרון העלה {extra}. "
                      f"סה\"כ הועלו: {len(_uploaded())}", flush=True)
                break
            time.sleep(args.interval)
            got = _sweep(api, args.repo, args.token, time.time())
            if got:
                print(f"   …עוד {got} parts (סה\"כ {len(_uploaded())})", flush=True)

    print(f"\n✅ done → https://huggingface.co/datasets/{args.repo}")


if __name__ == "__main__":
    main()
