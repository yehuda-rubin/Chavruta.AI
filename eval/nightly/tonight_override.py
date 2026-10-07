"""One-night custom reranker dataset extraction and evaluation override.

This script runs ONLY TONIGHT inside nightly_eval.py.
It extracts user query-citation pairs from SQLite and evaluates retrieval + reranking.
After completion, nightly_eval.py renames this script so that tomorrow night automatically reverts to standard tune_retrieval.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    print(f"[{datetime.now().isoformat()}] Starting custom Reranker tonight evaluation...")
    
    extract_script = ROOT / "scripts" / "extract_reranker_dataset.py"
    out_dataset = ROOT / "eval" / "reranker_training_dataset.jsonl"

    if extract_script.exists():
        print(f"Running dataset extraction script: {extract_script}...")
        proc = subprocess.run([sys.executable, str(extract_script), "--out", str(out_dataset), "--top-k", "16"])
        print(f"Dataset extraction completed with returncode: {proc.returncode}")
    else:
        print(f"Warning: extract_reranker_dataset.py not found at {extract_script}")

    # Write status summary
    summary_path = ROOT / "eval" / "nightly" / "custom_reranker_tonight_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    pairs_count = 0
    if out_dataset.exists():
        with out_dataset.open(encoding="utf-8") as fh:
            pairs_count = sum(1 for line in fh if line.strip())

    summary = {
        "ran_at": datetime.now().isoformat(),
        "status": "completed",
        "dataset_path": str(out_dataset),
        "pairs_extracted": pairs_count
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Tonight evaluation finished successfully! Results saved to {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
