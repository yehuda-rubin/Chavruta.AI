"""kaggle_nightly_eval.py — run the whole retrieval-tuning sweep in one sitting on a free Kaggle GPU.

WHY THIS EXISTS
----------------
scripts/nightly_eval.py runs harvest_pairs.py + tune_retrieval.py on the production box, throttled to
2 CPU cores inside a 23:00-07:00 window, because that box also serves live traffic — bge-m3 embedding
is the CPU-bound part of every request, so an unbounded batch job there competes with real users. That
throttle is the whole reason a full 8-knob sweep takes ~5 nights instead of one sitting (see that
script's docstring for the history of why).

None of that applies to a borrowed machine with no live traffic to protect. This runs the SAME two
scripts, unthrottled, on Kaggle's free GPU quota (T4x2 or P100, ~30h/week, sessions up to ~12h) — free,
and bge-m3 embedding on a GPU is an order of magnitude faster than on 2 CPU cores, so the whole sweep
should finish in well under an hour instead of a week.

Retrieval only — neither harvest_pairs.py nor tune_retrieval.py calls the LLM (verified: no
nebius/bridge/generation imports in either), so this never touches the Nebius generation budget and
needs no separate approval for that reason.

SETUP (in the Kaggle UI, before running)
------------------------------------------
1. New Notebook -> Settings (right sidebar) -> Accelerator: GPU T4 x2 (or P100) -> Internet: On.
   Internet must be on: this clones from GitHub and downloads a Qdrant binary + a ~17GB HF snapshot.
2. Only if Yehuda-Rubin/chavruta-commercial-index is a PRIVATE HF dataset: Add-ons -> Secrets -> add
   a secret named HF_TOKEN. If it's public, skip this — the script runs without it.
3. Paste this whole file into one cell and run it (or upload it as a .py and
   `!python kaggle_nightly_eval.py`).

WHAT YOU GET BACK
------------------
/kaggle/working/tuning_result/tuning_state.json — the winning knob values plus the held-out
confirmation for each. /kaggle/working/tuning_result/run.log — the full printed sweep (candidate
scores, the human-set veto, the final verdict). Download both from the notebook's Output/Files pane.
Nothing is applied automatically: tune_retrieval.py's own design is that these are load-bearing product
values a human reads and edits into src/chavruta/retrieval/hybrid.py by hand — this script doesn't
change that.

CAVEAT: the human-written veto set is smaller here than on the production box. eval/user_questions_v1.jsonl
(real user questions) is deliberately gitignored and never committed, so a fresh clone only carries
eval/torah_questions_v1.jsonl + eval/regressions_v1.jsonl to veto candidates against. Still real signal,
just thinner — for full parity, copy that file into eval/ yourself (e.g. via a private Kaggle Dataset)
before the tune step runs.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

import torch  # noqa: E402 — already in the Kaggle GPU image; import early to check CUDA up front

REPO_URL = os.environ.get("CHAVRUTA_REPO_URL", "https://github.com/yehuda-rubin/Chavruta.AI.git")
BRANCH = os.environ.get("CHAVRUTA_BRANCH", "main")
QDRANT_VER = "1.18.2"  # pinned to match the published snapshot's format

WORK = Path("/kaggle/working")
SCRATCH = WORK / "scratch"           # repo + qdrant storage + downloaded snapshot — large, disposable
REPO_DIR = SCRATCH / "Chavruta.AI"
RESULT_DIR = WORK / "tuning_result"  # small — this is what's actually worth downloading

TARGET_PAIRS = int(os.environ.get("HARVEST_TARGET", "5000"))
SAMPLE = int(os.environ.get("TUNE_SAMPLE", "1600"))  # same default the production nightly job settled
                                                       # on (see nightly_eval.py) after 800 measured
                                                       # too thin to clear MIN_HITS on the live pool


def sh(cmd: list[str], **kw) -> None:
    print(f"$ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True, **kw)


def hf_token() -> str | None:
    """Kaggle Secrets first (Add-ons -> Secrets -> HF_TOKEN), then env. None is fine if the HF
    dataset is public."""
    try:
        from kaggle_secrets import UserSecretsClient
        return UserSecretsClient().get_secret("HF_TOKEN")
    except Exception:
        return os.environ.get("HF_TOKEN")


def clone_repo() -> None:
    if REPO_DIR.exists():
        print(f"[skip] {REPO_DIR} already cloned")
        return
    SCRATCH.mkdir(parents=True, exist_ok=True)
    sh(["git", "clone", "--depth", "1", "--branch", BRANCH, REPO_URL, str(REPO_DIR)])


def install_deps() -> None:
    # torch is already in the Kaggle GPU image, with CUDA — do not reinstall it.
    sh([sys.executable, "-m", "pip", "install", "-q",
        "FlagEmbedding>=1.3", "qdrant-client>=1.12", "requests>=2.32",
        "huggingface_hub>=0.23", "tqdm>=4.66"])


def start_qdrant() -> subprocess.Popen:
    bin_path = Path("/usr/local/bin/qdrant")
    if not bin_path.exists():
        print("[bootstrap] downloading qdrant…", flush=True)
        url = (f"https://github.com/qdrant/qdrant/releases/download/v{QDRANT_VER}/"
               f"qdrant-x86_64-unknown-linux-musl.tar.gz")
        data = urllib.request.urlopen(url, timeout=180).read()
        tarfile.open(fileobj=io.BytesIO(data)).extractall("/usr/local/bin")
        bin_path.chmod(0o755)

    storage = SCRATCH / "qdrant_storage"
    snaps = SCRATCH / "qdrant_snapshots"
    storage.mkdir(parents=True, exist_ok=True)
    snaps.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ,
               QDRANT__STORAGE__STORAGE_PATH=str(storage),
               QDRANT__STORAGE__SNAPSHOTS_PATH=str(snaps),
               QDRANT__SERVICE__MAX_REQUEST_SIZE_MB="256")
    proc = subprocess.Popen(["/usr/local/bin/qdrant"], env=env)
    for _ in range(120):
        try:
            urllib.request.urlopen("http://localhost:6333/readyz", timeout=2)
            print("[bootstrap] qdrant ready", flush=True)
            return proc
        except Exception:
            time.sleep(1)
    raise RuntimeError("qdrant did not become ready in 120s")


def restore_snapshot() -> None:
    """Reuse the repo's own restore script, same-filesystem RAM-safe path: no docker here, so
    QDRANT_SNAPSHOT_DIR (not QDRANT_CONTAINER) — see restore_commercial_snapshot.py for why the plain
    HTTP-upload path is avoided (it buffers the whole ~17GB snapshot and can OOM a small box)."""
    env = dict(os.environ,
               CHAVRUTA_QDRANT_URL="http://localhost:6333",
               QDRANT_SNAPSHOT_DIR=str(SCRATCH / "qdrant_snapshots"))
    token = hf_token()
    if token:
        env["HF_TOKEN"] = token
    sh([sys.executable, "scripts/restore_commercial_snapshot.py"], cwd=REPO_DIR, env=env)


def run_step(args: list[str], *, env: dict, log) -> int:
    log.write(f"\n$ {' '.join(args)}\n")
    log.flush()
    proc = subprocess.Popen(args, cwd=REPO_DIR, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in proc.stdout:
        print(line, end="")
        log.write(line)
    return proc.wait()


def main() -> int:
    print(f"CUDA available: {torch.cuda.is_available()} "
          f"({torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none — check the notebook Accelerator setting'})")

    clone_repo()
    install_deps()
    qdrant = start_qdrant()
    try:
        restore_snapshot()

        # Deliberately staying on the snapshot's own "ssd" (on-disk) tier here, unlike
        # lightning_nightly_eval.py — Kaggle's session RAM is smaller and less predictable than a
        # rented Lightning Studio's, and an OOM-killed kernel loses the whole free GPU quota for
        # nothing. qdrant_to_ram.py exists (see that file) for a box where the RAM headroom is known.

        RESULT_DIR.mkdir(parents=True, exist_ok=True)
        state_path = RESULT_DIR / "tuning_state.json"
        log_path = RESULT_DIR / "run.log"
        pairs_path = REPO_DIR / "eval" / "harvested_pairs_v1.jsonl"

        run_env = dict(os.environ,
                       CHAVRUTA_QDRANT_MODE="server",
                       CHAVRUTA_QDRANT_URL="http://localhost:6333",
                       CHAVRUTA_COLLECTION="chavruta_commercial",
                       CHAVRUTA_MEM_TIER="ssd",
                       CHAVRUTA_EMBEDDING_DEVICE="cuda")

        with log_path.open("a", encoding="utf-8") as log:
            print("\n== harvesting ground-truth pairs (no LLM, GPU embedding) ==")
            rc = run_step([sys.executable, "scripts/harvest_pairs.py",
                           "--target", str(TARGET_PAIRS), "--out", str(pairs_path)],
                          env=run_env, log=log)
            if rc != 0:
                print(f"harvest_pairs.py failed (rc={rc}) — see {log_path}")
                return rc

            # No CPU/window throttle here, so unlike the production job this loops the WHOLE sweep in
            # one sitting instead of one knob per night. --state is kept anyway: it's what lets a
            # dropped Kaggle session resume from wherever it got to, at zero extra cost, instead of
            # restarting the sweep from scratch.
            print("\n== tuning (looping until every knob is done) ==")
            prev_done = -1
            for round_n in range(1, 21):  # generous cap — today's sweep is 8 knobs, one round each
                # run_tuning.py, not tune_retrieval.py directly: same sweep, same real hybrid.py, but
                # with a from-scratch GPU embedder + disk cache standing in for BgeM3Embedding — see
                # that file's docstring (avoids re-embedding identical queries on every one of the
                # ~8 scoring passes a knob makes, and across the fresh subprocess each round here is).
                rc = run_step([sys.executable, "scripts/run_tuning.py",
                               "--pairs", str(pairs_path), "--sample", str(SAMPLE),
                               "--state", str(state_path)],
                              env=run_env, log=log)
                if rc != 0:
                    print(f"run_tuning.py failed (rc={rc}) — see {log_path}")
                    return rc
                done = json.loads(state_path.read_text(encoding="utf-8"))["done"]
                print(f"[round {round_n}] {len(done)} knob(s) done: {', '.join(done) or '(none yet)'}")
                if len(done) == prev_done:
                    print("no further progress this round — sweep complete")
                    break
                prev_done = len(done)
    finally:
        qdrant.terminate()

    print(f"\nDone. Download {RESULT_DIR} from the notebook's Output pane — "
          f"tuning_state.json has the winning values, run.log has the full sweep.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
