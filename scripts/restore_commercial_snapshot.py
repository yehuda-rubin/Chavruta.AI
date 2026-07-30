"""restore_commercial_snapshot.py — pull the prebuilt commercial index home and restore it.

The counterpart to index_commercial_job.py: instead of re-embedding + re-indexing (hours), download
the Qdrant snapshot the job published to HF and recover it into your local Qdrant server in seconds.

    # start your Qdrant (docker compose up -d qdrant), then:
    python scripts/restore_commercial_snapshot.py
    # → collection 'chavruta_commercial' is live. Point the app at it:
    #   CHAVRUTA_COLLECTION=chavruta_commercial

⚠️ This is the ONLY correct way to populate the production collection. `load_all_indexes.py`
   builds a DIFFERENT, non-commercial collection (`chavruta_mixed`) and must never be pointed at
   `chavruta_commercial` — see that script's own warning.

Env:
  INDEX_REPO           HF dataset with the snapshot (default Yehuda-Rubin/chavruta-commercial-index)
  CHAVRUTA_QDRANT_URL  local Qdrant (default http://localhost:6333)
  HF_TOKEN             only needed if the dataset is private
  QDRANT_CONTAINER     name of the Qdrant Docker container (e.g. `chavruta-qdrant`, matching
                       docker-compose.yml's container_name). When set, restores the RAM-SAFE way:
                       `docker cp` the snapshot into the container and recover from that local
                       file, instead of uploading it over HTTP. The direct upload buffers the
                       WHOLE snapshot (tens of GB) inside Qdrant's request pipeline, which drives
                       a machine with less RAM than the snapshot into swap or OOM — verified on a
                       15.7GB box (see scripts/restore_commercial_tonight.ps1, the Windows-only
                       script this generalises). Always set this on a small VM (e.g. an Oracle
                       Cloud Always Free instance with 12GB RAM); leave unset only on a box with
                       RAM well above the snapshot size.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

INDEX_REPO = os.environ.get("INDEX_REPO", "Yehuda-Rubin/chavruta-commercial-index")
QDRANT_URL = os.environ.get("CHAVRUTA_QDRANT_URL", "http://localhost:6333").rstrip("/")
HF_TOKEN = os.environ.get("HF_TOKEN")
QDRANT_CONTAINER = os.environ.get("QDRANT_CONTAINER", "").strip()


def _restore_via_local_file(collection: str, snap_local: str) -> None:
    """RAM-safe path: copy the already-downloaded snapshot INTO the Qdrant container's own
    filesystem, then have Qdrant recover from that local path — it streams from disk instead of
    buffering an HTTP request body, which is what makes this safe on a small machine."""
    import requests

    in_container = f"/qdrant/snapshots/{collection}/{Path(snap_local).name}"
    print(f"copying snapshot into container {QDRANT_CONTAINER!r} (RAM-safe path)…")
    subprocess.run(["docker", "exec", QDRANT_CONTAINER, "mkdir", "-p",
                    f"/qdrant/snapshots/{collection}"], check=True)
    subprocess.run(["docker", "cp", snap_local, f"{QDRANT_CONTAINER}:{in_container}"], check=True)
    print("recovering from the local file (the light step)…")
    r = requests.put(f"{QDRANT_URL}/collections/{collection}/snapshots/recover",
                     json={"location": f"file://{in_container}", "priority": "snapshot"},
                     timeout=3600)
    r.raise_for_status()


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
    print(f"downloaded snapshot ({size_gb:.2f} GB)")

    if QDRANT_CONTAINER:
        _restore_via_local_file(collection, snap_local)
    else:
        print("uploading to Qdrant over HTTP (set QDRANT_CONTAINER for the RAM-safe path)…")
        with Path(snap_local).open("rb") as f:
            r = requests.post(
                f"{QDRANT_URL}/collections/{collection}/snapshots/upload?priority=snapshot",
                files={"snapshot": (Path(snap_rel).name, f)}, timeout=3600)
        r.raise_for_status()
    print(f"✅ '{collection}' restored. Set CHAVRUTA_COLLECTION={collection} and run the app.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
