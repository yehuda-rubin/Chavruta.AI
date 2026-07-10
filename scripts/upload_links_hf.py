# -*- coding: utf-8 -*-
"""upload_links_hf.py — publish the link graph to the SAME HF account as the RAG index.

The RAG ships as ``Yehuda-Rubin/chavruta-index-<category>`` datasets. The link graph is one global,
cross-category artifact, so it gets a sibling dataset repo ``Yehuda-Rubin/chavruta-index-links`` —
so the linker travels WITH the RAG and loads wherever the corpus is deployed (deployment-agnostic).

Uploads (idempotent — skips files already present unless --force):
  links_corpus.jsonl  — portable canonical commentary→base graph (1.26M edges)
  links_corpus.db     — on-disk graph (LinkStore) for O(1)-RAM runtime
  ref_index.db        — canonical-ref → chunk-ref resolver (RefIndex)

    .venv/Scripts/python.exe scripts/upload_links_hf.py --token $HF_TOKEN
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
NAMESPACE = "Yehuda-Rubin"
DEFAULT_REPO = f"{NAMESPACE}/chavruta-index-links"
FILES = ["links_corpus.jsonl", "links_corpus.db", "ref_index.db"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--token", default=os.environ.get("HF_TOKEN"))
    ap.add_argument("--force", action="store_true", help="re-upload even if the file already exists")
    args = ap.parse_args()
    if not args.token:
        raise SystemExit("no HF token — pass --token or set HF_TOKEN")

    from huggingface_hub import HfApi, create_repo
    api = HfApi()
    create_repo(args.repo, repo_type="dataset", exist_ok=True, token=args.token)
    have = set(api.list_repo_files(args.repo, repo_type="dataset", token=args.token))

    for fname in FILES:
        local = REPO / "data" / fname
        if not local.exists():
            print(f"  ⚠ skip {fname} (not built — run build_link_index.py / build_corpus_links.py)")
            continue
        if fname in have and not args.force:
            print(f"  = {fname} already in {args.repo} (use --force to replace)")
            continue
        mb = local.stat().st_size / 1e6
        print(f"  ↑ uploading {fname} ({mb:.0f} MB) → {args.repo} …", flush=True)
        api.upload_file(path_or_fileobj=str(local), path_in_repo=fname,
                        repo_id=args.repo, repo_type="dataset", token=args.token)
    print(f"\n✅ link graph → https://huggingface.co/datasets/{args.repo}")


if __name__ == "__main__":
    main()
