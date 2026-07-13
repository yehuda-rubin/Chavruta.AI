# -*- coding: utf-8 -*-
"""upload_index_from_zips.py — publish pre-built RAG indexes (zips in ~/Downloads) to HF.

Each zip holds the store-agnostic index files (corpus_vectors.npy [+ corpus_sparse.jsonl]
+ corpus_meta.jsonl). We publish each category to its OWN dataset repo, matching the existing
convention `Yehuda-Rubin/chavruta-index-<slug>` (same as chavruta-index-halacha) — the 3 files
live at the repo root, so categories never collide.

Idempotent: skips a file already present in the target repo (unless --force).
Disk-friendly: extracts ONE zip at a time to a temp dir, uploads, then deletes the temp.

Run:
    # all mapped categories:
    python scripts/upload_index_from_zips.py
    # just one:
    python scripts/upload_index_from_zips.py --only shut
"""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

# zip in ~/Downloads  ->  HF slug (repo = Yehuda-Rubin/chavruta-index-<slug>)
ZIP_TO_SLUG = {
    "shut_vectors.zip": "shut",
    "gemara_vectors.zip": "gemara",
    "mishnah_vectors.zip": "mishnah",
    "corpus_embeddings.zip": "tanakh",   # dense-only (no sparse) — the original Tanakh corpus
}
INDEX_FILES = ("corpus_vectors.npy", "corpus_sparse.jsonl", "corpus_meta.jsonl")
NAMESPACE = "Yehuda-Rubin"


def publish_zip(api, zip_path: Path, slug: str, token: str | None, force: bool) -> None:
    from huggingface_hub import create_repo

    repo = f"{NAMESPACE}/chavruta-index-{slug}"
    print(f"\n=== {zip_path.name}  →  {repo} ===", flush=True)
    create_repo(repo, repo_type="dataset", exist_ok=True, token=token)
    have = set(api.list_repo_files(repo, repo_type="dataset", token=token))

    with zipfile.ZipFile(zip_path) as zf:
        members = [m for m in zf.namelist() if Path(m).name in INDEX_FILES]
        tmp = Path(tempfile.mkdtemp(prefix=f"idx_{slug}_"))
        try:
            for m in members:
                fname = Path(m).name
                if fname in have and not force:
                    print(f"   ⏭️  {fname} כבר במאגר — מדלג", flush=True)
                    continue
                print(f"   📦 מחלץ {fname} …", flush=True)
                zf.extract(m, tmp)
                local = tmp / m
                mb = local.stat().st_size / 1e6
                print(f"   ⬆️  {mb:9.1f} MB  {fname}", flush=True)
                api.upload_file(path_or_fileobj=str(local), path_in_repo=fname,
                                repo_id=repo, repo_type="dataset", token=token)
                local.unlink(missing_ok=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"   ✅ {slug} → https://huggingface.co/datasets/{repo}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--downloads", default=str(Path.home() / "Downloads"))
    ap.add_argument("--only", default=None, help="slug יחיד (shut/gemara/mishnah/tanakh)")
    ap.add_argument("--force", action="store_true", help="העלה גם אם הקובץ כבר במאגר")
    ap.add_argument("--token", default=os.environ.get("HF_TOKEN"))
    args = ap.parse_args()

    from huggingface_hub import HfApi

    api = HfApi()
    dl = Path(args.downloads)
    todo = {z: s for z, s in ZIP_TO_SLUG.items() if args.only in (None, s)}
    if not todo:
        raise SystemExit(f"--only {args.only!r} לא מוכר. בחר מתוך: {sorted(ZIP_TO_SLUG.values())}")

    for zip_name, slug in todo.items():
        zp = dl / zip_name
        if not zp.exists():
            print(f"⚠️  לא נמצא {zp} — מדלג", flush=True)
            continue
        publish_zip(api, zp, slug, args.token, args.force)

    print("\n✅ done")


if __name__ == "__main__":
    main()
