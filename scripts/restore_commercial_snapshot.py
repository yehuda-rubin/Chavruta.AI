"""restore_commercial_snapshot.py — pull the prebuilt commercial index home and restore it.

The counterpart to index_commercial_job.py: instead of re-embedding + re-indexing (hours), download
the Qdrant snapshot the job published to HF and recover it into your local Qdrant server in seconds.

    # start your Qdrant (docker compose up -d qdrant), then:
    python scripts/restore_commercial_snapshot.py
    # → collection 'chavruta_commercial' is live. Point the app at it:
    #   CHAVRUTA_COLLECTION=chavruta_commercial

Env:
  INDEX_REPO           HF dataset with the snapshot (default Yehuda-Rubin/chavruta-commercial-index)
  CHAVRUTA_QDRANT_URL  local Qdrant (default http://localhost:6333)
  HF_TOKEN             only needed if the dataset is private
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

INDEX_REPO = os.environ.get("INDEX_REPO", "Yehuda-Rubin/chavruta-commercial-index")
QDRANT_URL = os.environ.get("CHAVRUTA_QDRANT_URL", "http://localhost:6333").rstrip("/")
HF_TOKEN = os.environ.get("HF_TOKEN")


def main() -> int:
    import requests
    from huggingface_hub import hf_hub_download

    manifest_path = hf_hub_download(repo_id=INDEX_REPO, filename="manifest.json",
                                    repo_type="dataset", token=HF_TOKEN)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    collection = manifest["collection"]
    snap_rel = manifest["snapshot"]                 # e.g. "snapshots/<name>.snapshot"
    print(f"restoring '{collection}' from {INDEX_REPO}/{snap_rel}")

    snap_local = hf_hub_download(repo_id=INDEX_REPO, filename=snap_rel,
                                 repo_type="dataset", token=HF_TOKEN)
    size_gb = Path(snap_local).stat().st_size / 1e9
    print(f"downloaded snapshot ({size_gb:.2f} GB) — uploading to Qdrant…")

    # Recover by uploading the snapshot file to the server (priority=snapshot: the snapshot wins).
    with Path(snap_local).open("rb") as f:
        r = requests.post(
            f"{QDRANT_URL}/collections/{collection}/snapshots/upload?priority=snapshot",
            files={"snapshot": (Path(snap_rel).name, f)}, timeout=3600)
    r.raise_for_status()
    print(f"✅ '{collection}' restored. Set CHAVRUTA_COLLECTION={collection} and run the app.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
