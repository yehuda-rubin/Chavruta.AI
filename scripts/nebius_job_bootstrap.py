"""nebius_job_bootstrap.py — injected entrypoint for the commercial-index Serverless AI Job.

Runs inside a public PyTorch image (so no custom image build/push): installs the extra deps, brings
up a co-located Qdrant, pulls the project source from the private HF `chavruta-src` dataset, and runs
scripts/index_commercial_job.py. Injected via `nebius ai job create --inject-file` (<64 KiB).

Env it relies on (set on the job): HF_TOKEN, plus everything index_commercial_job.py reads
(BATCH, TIERS, INDEX_REPO, CHAVRUTA_COLLECTION, CHAVRUTA_MEM_TIER, COMMERCIAL_NAMESPACE, …).
"""

import io
import os
import subprocess
import sys
import tarfile
import time
import urllib.request

QDRANT_VER = "1.18.2"
SRC_REPO = os.environ.get("SRC_REPO", "Yehuda-Rubin/chavruta-src")
WORK = "/workspace"


def sh(cmd: str) -> None:
    print(f"$ {cmd}", flush=True)
    subprocess.check_call(cmd, shell=True)


def main() -> int:
    os.makedirs(WORK, exist_ok=True)

    # 1. Extra Python deps (torch is already in the pytorch base image).
    sh(f'{sys.executable} -m pip install -q "FlagEmbedding==1.3.4" "transformers==4.44.2" '
       f'"qdrant-client==1.12.1" huggingface_hub numpy requests')

    # 2. Qdrant binary (pinned to the app's version so the snapshot restores cleanly). Use the MUSL
    # static build — it has no glibc dependency, so it runs on any base image (the gnu build needs
    # GLIBC 2.38, newer than the pytorch image ships).
    print("[bootstrap] downloading qdrant…", flush=True)
    url = f"https://github.com/qdrant/qdrant/releases/download/v{QDRANT_VER}/qdrant-x86_64-unknown-linux-musl.tar.gz"
    data = urllib.request.urlopen(url, timeout=180).read()
    tarfile.open(fileobj=io.BytesIO(data)).extractall("/usr/local/bin")
    os.chmod("/usr/local/bin/qdrant", 0o755)

    # 3. Start Qdrant with on-disk storage + snapshots on the big job disk.
    os.environ["QDRANT__STORAGE__STORAGE_PATH"] = f"{WORK}/qdrant_storage"
    os.environ["QDRANT__STORAGE__SNAPSHOTS_PATH"] = f"{WORK}/qdrant_snapshots"
    os.environ["QDRANT__SERVICE__MAX_REQUEST_SIZE_MB"] = "256"   # default 32MB is too small for batches
    os.makedirs(os.environ["QDRANT__STORAGE__STORAGE_PATH"], exist_ok=True)
    os.makedirs(os.environ["QDRANT__STORAGE__SNAPSHOTS_PATH"], exist_ok=True)
    qdrant = subprocess.Popen(["/usr/local/bin/qdrant"])
    for _ in range(120):
        try:
            urllib.request.urlopen("http://localhost:6333/readyz", timeout=2)
            print("[bootstrap] qdrant ready", flush=True)
            break
        except Exception:
            time.sleep(1)
    else:
        print("[bootstrap] qdrant did not become ready", file=sys.stderr, flush=True)
        return 1

    # 4. Pull the project source (private HF dataset) and unpack it.
    from huggingface_hub import hf_hub_download
    p = hf_hub_download(SRC_REPO, "chavruta_src.tgz", repo_type="dataset", token=os.environ["HF_TOKEN"])
    tarfile.open(p).extractall(f"{WORK}/app")

    # 5. Run the job. No `pip install -e` — the base image's Python (3.10) is below the package's
    # declared >=3.11, and it isn't needed: index_commercial_job.py adds src/ to sys.path itself, and
    # we also set PYTHONPATH so `import chavruta` resolves regardless.
    os.chdir(f"{WORK}/app")
    env = dict(os.environ, PYTHONPATH=f"{WORK}/app/src")
    rc = subprocess.call([sys.executable, "scripts/index_commercial_job.py"], env=env)

    qdrant.terminate()
    return rc


if __name__ == "__main__":
    sys.exit(main())
