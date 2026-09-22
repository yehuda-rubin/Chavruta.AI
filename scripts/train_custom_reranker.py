"""Train Custom Reranker for Chavruta.AI (mMiniLMv2-L6 / mMiniLMv2-L12).

Designed to run on Kaggle / Google Colab (GPU T4 free tier) or local GPU.

Usage:
    python scripts/train_custom_reranker.py --dataset eval/reranker_training_dataset.jsonl --epochs 3
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

try:
    from sentence_transformers import CrossEncoder, InputExample
    from torch.utils.data import DataLoader
except ImportError:
    print("Error: sentence-transformers is required. Install via: pip install sentence-transformers torch")


def load_dataset(jsonl_path: Path) -> list[dict]:
    """Load JSONL dataset containing {question, passage, label}."""
    examples = []
    with jsonl_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            item = json.loads(line)
            examples.append(item)
    return examples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="eval/reranker_training_dataset.jsonl", help="Path to input dataset JSONL")
    parser.add_argument("--model-name", default="cross-encoder/mmarco-mMiniLMv2-L6-H384-v1", help="Base model architecture")
    parser.add_argument("--output-dir", default="models/custom_reranker_mMiniLMv2_L6", help="Directory to save trained model")
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=16, help="Training batch size")
    parser.add_argument("--lr", type=float, default=2e-5, help="Learning rate")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"Error: Dataset file not found at {dataset_path}")
        return 1

    print(f"Loading dataset from {dataset_path}...")
    raw_data = load_dataset(dataset_path)
    print(f"Loaded {len(raw_data)} total training pairs.")

    # Shuffle & split train/val
    random.seed(42)
    random.shuffle(raw_data)
    
    split_idx = int(len(raw_data) * 0.85)
    train_data = raw_data[:split_idx]
    val_data = raw_data[split_idx:]

    print(f"Train split: {len(train_data)} pairs | Validation split: {len(val_data)} pairs")

    train_examples = [
        InputExample(texts=[item["question"], item["passage"]], label=float(item["label"]))
        for item in train_data
    ]

    train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=args.batch_size)

    print(f"Initializing CrossEncoder with base model: {args.model_name}...")
    model = CrossEncoder(args.model_name, num_labels=1)

    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    warmup_steps = int(len(train_dataloader) * args.epochs * 0.1)

    print("\nStarting model training...")
    model.fit(
        train_dataloader=train_dataloader,
        epochs=args.epochs,
        warmup_steps=warmup_steps,
        optimizer_params={"lr": args.lr},
        output_path=str(output_path),
        save_best_model=True
    )

    print(f"\nTraining complete! Fine-tuned model saved to {output_path}")

    # Evaluate validation loss / score
    val_pairs = [(item["question"], item["passage"]) for item in val_data]
    val_labels = [float(item["label"]) for item in val_data]

    if val_pairs:
        predictions = model.predict(val_pairs)
        print("\nValidation Sample Predictions:")
        for idx in range(min(5, len(val_pairs))):
            print(f"Q: {val_pairs[idx][0][:40]}... | Target: {val_labels[idx]} | Pred Score: {predictions[idx]:.4f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
