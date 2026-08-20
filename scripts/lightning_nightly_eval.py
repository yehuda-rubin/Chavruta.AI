"""lightning_nightly_eval.py — run the retrieval-tuning sweep on a rented Lightning AI H100.

WHY THIS EXISTS, AND WHY IT'S NOT JUST kaggle_nightly_eval.py
----------------------------------------------------------------
Same job as kaggle_nightly_eval.py (see that file for the full "why unthrottled beats the 5-night
production window" background) — harvest_pairs.py + tune_retrieval.py, unthrottled, against the
restored chavruta_commercial snapshot, with the collection moved to the "16gb" RAM tier first
(qdrant_to_ram.py) so Qdrant's on-disk HNSW graph search stops being the bottleneck.

The difference is money: Kaggle's T4x2 is free with no real ceiling (~30h/week). Lightning's H100 is
metered against a small monthly credit (~$15 ≈ 3-5.5 H100-hours at $3-5.5/hr) — burn it on downloading
a 17GB snapshot and re-laying Qdrant segments and there may be nothing left for the part an H100
actually helps with.

So this splits into two phases, meant to run on TWO DIFFERENT machine types of the SAME Studio
(Lightning lets you switch CPU<->GPU on one Studio with no data loss — the picker is top-right in the
Studio UI):

    --phase setup   on a CPU machine (free): clone, restore the snapshot, move to the RAM tier,
                     harvest pairs. None of this touches a GPU — harvest_pairs.py's own docstring
                     says "no LLM, CPU only", and restoring/re-laying Qdrant segments is disk I/O.
    --phase tune    on an H100 machine (metered): starts Qdrant against the SAME already-migrated
                     storage (no re-restore) and runs the tuning sweep — the actually
                     compute-bound, GPU-worth-paying-for part.
    --phase all     both in one sitting, one machine — simpler, but pays H100 rates for the setup
                     time too. Default only because it's the safe fallback if you don't want to
                     bother switching machine types; --phase setup then --phase tune is what actually
                     saves the credit.

SETUP (once, in the Lightning UI)
------------------------------------
1. New Studio. Set a Studio environment variable HF_TOKEN only if
   Yehuda-Rubin/chavruta-commercial-index is a PRIVATE HF dataset (Studio Settings -> Environment
   variables) — if it's public, skip this.
2. Leave the machine on its default CPU tier for `--phase setup`.
3. Paste this file into a terminal/notebook cell in the Studio and run:
       python lightning_nightly_eval.py --phase setup
4. When it prints "switch to an H100 now", use the compute picker (top-right) to attach an H100,
   then run:
       python lightning_nightly_eval.py --phase tune

WHAT YOU GET BACK
------------------
<WORK>/tuning_result/tuning_state.json — the winning knob values + held-out confirmation.
<WORK>/tuning_result/run.log — the full printed sweep. Nothing is applied automatically: a human
reads the numbers and edits src/chavruta/retrieval/hybrid.py by hand — see that file's own printed
verdict at the end of a run ("Apply by editing the constants...").

CAVEAT: the human-written veto set is thinner than production's. eval/user_questions_v1.jsonl (real
user questions) is gitignored and never committed, so a fresh clone only carries
eval/torah_questions_v1.jsonl + eval/regressions_v1.jsonl. Still real signal, just smaller — for full
parity, drop that file into eval/ yourself before --phase setup's harvest step runs.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

REPO_URL = os.environ.get("CHAVRUTA_REPO_URL", "https://github.com/yehuda-rubin/Chavruta.AI.git")
BRANCH = os.environ.get("CHAVRUTA_BRANCH", "main")
QDRANT_VER = "1.18.2"  # pinned to match the published snapshot's format

# Lightning Studios persist /teamspace/studios/this_studio across machine-type switches; fall back to
# the cwd if that path doesn't exist (e.g. run outside a Studio, or the convention has moved).
_LIGHTNING_HOME = Path("/teamspace/studios/this_studio")
WORK = _LIGHTNING_HOME if _LIGHTNING_HOME.is_dir() else Path.cwd()
SCRATCH = WORK / "scratch"           # repo + qdrant storage + downloaded snapshot — large, disposable
REPO_DIR = SCRATCH / "Chavruta.AI"
RESULT_DIR = WORK / "tuning_result"  # small — this is what's actually worth downloading
QDRANT_STORAGE = SCRATCH / "qdrant_storage"
QDRANT_SNAPS = SCRATCH / "qdrant_snapshots"

TARGET_PAIRS = int(os.environ.get("HARVEST_TARGET", "5000"))
SAMPLE = int(os.environ.get("TUNE_SAMPLE", "1600"))


def sh(cmd: list[str], **kw) -> None:
    print(f"$ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True, **kw)


def clone_repo() -> None:
    if REPO_DIR.exists():
        print(f"[skip] {REPO_DIR} already cloned")
        return
    SCRATCH.mkdir(parents=True, exist_ok=True)
    sh(["git", "clone", "--depth", "1", "--branch", BRANCH, REPO_URL, str(REPO_DIR)])


def install_deps() -> None:
    # torch is already in Lightning's default image, CPU or GPU build depending on the attached
    # machine — do not reinstall it; installing over it risks swapping a CUDA build for a CPU one.
    sh([sys.executable, "-m", "pip", "install", "-q",
        "FlagEmbedding>=1.3", "qdrant-client>=1.12", "requests>=2.32",
        "huggingface_hub>=0.23", "tqdm>=4.66"])


def start_qdrant() -> subprocess.Popen:
    """Start Qdrant against QDRANT_STORAGE. Safe to call in either phase: in `setup` the directory is
    empty (fresh collection created by the snapshot restore that follows); in `tune` it already holds
    the RAM-tier-migrated collection from `setup`, and Qdrant loads it as configured — the RAM-tier
    change made via qdrant_to_ram.py is persisted in the collection's own on-disk config, not
    something this process needs to re-apply."""
    bin_path = Path("/usr/local/bin/qdrant")
    if not bin_path.exists():
        print("[bootstrap] downloading qdrant…", flush=True)
        url = (f"https://github.com/qdrant/qdrant/releases/download/v{QDRANT_VER}/"
               f"qdrant-x86_64-unknown-linux-musl.tar.gz")
        data = urllib.request.urlopen(url, timeout=180).read()
        tarfile.open(fileobj=io.BytesIO(data)).extractall("/usr/local/bin")
        bin_path.chmod(0o755)

    QDRANT_STORAGE.mkdir(parents=True, exist_ok=True)
    QDRANT_SNAPS.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ,
               QDRANT__STORAGE__STORAGE_PATH=str(QDRANT_STORAGE),
               QDRANT__STORAGE__SNAPSHOTS_PATH=str(QDRANT_SNAPS),
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
    """Same-filesystem RAM-safe path (no docker on a Studio): QDRANT_SNAPSHOT_DIR, not
    QDRANT_CONTAINER — see restore_commercial_snapshot.py for why the plain HTTP-upload path is
    avoided (it buffers the whole ~17GB snapshot and can OOM a small box)."""
    env = dict(os.environ,
               CHAVRUTA_QDRANT_URL="http://localhost:6333",
               QDRANT_SNAPSHOT_DIR=str(QDRANT_SNAPS))
    token = os.environ.get("HF_TOKEN")  # set as a Studio environment variable, if the dataset is private
    if token:
        env["HF_TOKEN"] = token
    sh([sys.executable, "scripts/restore_commercial_snapshot.py"], cwd=REPO_DIR, env=env)


def move_to_ram_tier() -> None:
    env = dict(os.environ, CHAVRUTA_QDRANT_URL="http://localhost:6333",
               CHAVRUTA_COLLECTION="chavruta_commercial")
    sh([sys.executable, "scripts/qdrant_to_ram.py", "--tier", "16gb", "--wait"],
       cwd=REPO_DIR, env=env)


def run_step(args: list[str], *, env: dict, log) -> int:
    log.write(f"\n$ {' '.join(args)}\n")
    log.flush()
    proc = subprocess.Popen(args, cwd=REPO_DIR, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in proc.stdout:
        print(line, end="")
        log.write(line)
    return proc.wait()


def phase_setup() -> int:
    clone_repo()
    install_deps()
    qdrant = start_qdrant()
    try:
        restore_snapshot()
        move_to_ram_tier()

        RESULT_DIR.mkdir(parents=True, exist_ok=True)
        pairs_path = REPO_DIR / "eval" / "harvested_pairs_v1.jsonl"
        log_path = RESULT_DIR / "run.log"
        # CPU here on purpose — this phase is meant to run before an H100 is attached, and
        # harvest_pairs.py needs no embedding at all (ref-string parsing + a keyword-index lookup).
        env = dict(os.environ, CHAVRUTA_QDRANT_MODE="server",
                   CHAVRUTA_QDRANT_URL="http://localhost:6333",
                   CHAVRUTA_COLLECTION="chavruta_commercial")
        with log_path.open("a", encoding="utf-8") as log:
            print("\n== harvesting ground-truth pairs (no LLM, no GPU needed) ==")
            rc = run_step([sys.executable, "scripts/harvest_pairs.py",
                           "--target", str(TARGET_PAIRS), "--out", str(pairs_path)],
                          env=env, log=log)
        if rc != 0:
            print(f"harvest_pairs.py failed (rc={rc}) — see {log_path}")
            return rc
    finally:
        qdrant.terminate()

    print("\nsetup done. Switch this Studio to an H100 (compute picker, top-right), then run:\n"
          "    python lightning_nightly_eval.py --phase tune")
    return 0


def phase_tune() -> int:
    if not QDRANT_STORAGE.exists():
        print(f"no Qdrant storage at {QDRANT_STORAGE} — run --phase setup first "
              f"(on a CPU machine, to avoid paying H100 rates for it).")
        return 1
    pairs_path = REPO_DIR / "eval" / "harvested_pairs_v1.jsonl"
    if not pairs_path.exists():
        print(f"no harvested pairs at {pairs_path} — run --phase setup first.")
        return 1

    import torch
    print(f"CUDA available: {torch.cuda.is_available()} "
          f"({torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none — attach the H100 first'})")

    install_deps()  # idempotent; harmless if the machine switch reset the environment
    qdrant = start_qdrant()
    try:
        RESULT_DIR.mkdir(parents=True, exist_ok=True)
        state_path = RESULT_DIR / "tuning_state.json"
        log_path = RESULT_DIR / "run.log"
        run_env = dict(os.environ,
                       CHAVRUTA_QDRANT_MODE="server",
                       CHAVRUTA_QDRANT_URL="http://localhost:6333",
                       CHAVRUTA_COLLECTION="chavruta_commercial",
                       CHAVRUTA_EMBEDDING_DEVICE="cuda")
        with log_path.open("a", encoding="utf-8") as log:
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

    print(f"\nDone. {RESULT_DIR} has tuning_state.json (winning values) and run.log (the full sweep). "
          f"You can switch this Studio back to CPU now — the H100 is no longer needed.")
    return 0


def phase_all() -> int:
    rc = phase_setup()
    if rc != 0:
        return rc
    return phase_tune()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", choices=["setup", "tune", "all"], default="all",
                    help="setup+tune on separate machine types is what actually saves H100 credit "
                         "(see this file's docstring); 'all' is the simpler one-machine fallback")
    args = ap.parse_args()
    return {"setup": phase_setup, "tune": phase_tune, "all": phase_all}[args.phase]()


if __name__ == "__main__":
    raise SystemExit(main())
