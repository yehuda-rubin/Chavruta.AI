"""Convert fine-tuned CrossEncoder model to ONNX dynamic INT8 format.

This script:
1. Loads PyTorch model/tokenizer from model directory or HuggingFace ID.
2. Exports PyTorch CrossEncoder graph to ONNX model.onnx.
3. Applies dynamic INT8 quantization (reduces size from ~85MB to ~22MB).
4. Runs CPU latency benchmark on 16 test pairs.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np

try:
    import onnxruntime as ort
    from onnxruntime.quantization import QuantType, quantize_dynamic
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
except ImportError:
    print("Error: Required dependencies missing. Install via: pip install onnxruntime transformers torch")


def export_to_onnx(model_dir: str, onnx_fp32_path: Path):
    """Export PyTorch CrossEncoder to ONNX format."""
    print(f"Loading PyTorch model from {model_dir}...")
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir)
    model.eval()

    dummy_input = tokenizer(
        ["מה המקור למצוות ציצית?"],
        ["במדבר פרק טו פסוק לח: דבר אל בני ישראל ואמרת אליהם ועשו להם ציצית"],
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=512
    )

    input_names = ["input_ids", "attention_mask"]
    dynamic_axes = {
        "input_ids": {0: "batch_size", 1: "sequence_length"},
        "attention_mask": {0: "batch_size", 1: "sequence_length"},
        "logits": {0: "batch_size"}
    }

    if "token_type_ids" in dummy_input:
        input_names.append("token_type_ids")
        dynamic_axes["token_type_ids"] = {0: "batch_size", 1: "sequence_length"}

    inputs_tuple = tuple(dummy_input[k] for k in input_names)

    print(f"Exporting ONNX FP32 graph to {onnx_fp32_path}...")
    torch.onnx.export(
        model,
        inputs_tuple,
        str(onnx_fp32_path),
        input_names=input_names,
        output_names=["logits"],
        dynamic_axes=dynamic_axes,
        opset_version=14
    )
    tokenizer.save_pretrained(onnx_fp32_path.parent)
    print("FP32 export complete.")


def quantize_to_int8(fp32_path: Path, int8_path: Path):
    """Apply ONNX dynamic INT8 quantization."""
    print(f"Quantizing ONNX FP32 -> Dynamic INT8 ({int8_path.name})...")
    quantize_dynamic(
        model_input=str(fp32_path),
        model_output=str(int8_path),
        weight_type=QuantType.QUInt8
    )
    size_fp32 = fp32_path.stat().st_size / (1024 * 1024)
    size_int8 = int8_path.stat().st_size / (1024 * 1024)
    print(f"Quantization complete! FP32: {size_fp32:.2f}MB -> INT8: {size_int8:.2f}MB")


def benchmark_onnx_cpu(onnx_model_path: Path, num_pairs: int = 16, runs: int = 20):
    """Benchmark CPU inference latency for N pairs."""
    print(f"\nBenchmarking ONNX CPU inference for batch of {num_pairs} pairs ({runs} runs)...")
    tokenizer = AutoTokenizer.from_pretrained(onnx_model_path.parent)
    
    session_options = ort.SessionOptions()
    session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    
    session = ort.InferenceSession(str(onnx_model_path), session_options, providers=["CPUExecutionProvider"])

    queries = ["מה אמר רבא בבא מציעא?" for _ in range(num_pairs)]
    passages = [f"בבא מציעא דף ב עמוד א: שניים אוחזין בטלית זה אומר אני מצאתיה וזה אומר אני מצאתיה..." for _ in range(num_pairs)]

    inputs = tokenizer(queries, passages, padding=True, truncation=True, max_length=256, return_tensors="np")
    onnx_inputs = {k: v.astype(np.int64) for k, v in inputs.items()}

    # Warmup
    session.run(None, onnx_inputs)

    latencies = []
    for _ in range(runs):
        t0 = time.perf_counter()
        session.run(None, onnx_inputs)
        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000)

    p50 = np.median(latencies)
    p95 = np.percentile(latencies, 95)
    mean_lat = np.mean(latencies)

    print(f"Results for {num_pairs} pairs on CPU:")
    print(f"  • Median (p50): {p50:.2f} ms")
    print(f"  • 95th Percentile (p95): {p95:.2f} ms")
    print(f"  • Mean: {mean_lat:.2f} ms")
    if p95 <= 1000:
        print(f"✅ PASSED constraint (≤ 1000 ms limit)! Actual: {p95:.2f} ms")
    else:
        print(f"⚠️ EXCEEDED 1000ms constraint! Actual: {p95:.2f} ms")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", default="models/custom_reranker_mMiniLMv2_L6", help="Path to PyTorch model dir")
    parser.add_argument("--output-dir", default="models/onnx_reranker_int8", help="Output path for ONNX INT8 model")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    fp32_path = out_dir / "model_fp32.onnx"
    int8_path = out_dir / "model_int8.onnx"

    export_to_onnx(args.model_dir, fp32_path)
    quantize_to_int8(fp32_path, int8_path)
    benchmark_onnx_cpu(int8_path, num_pairs=16)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
