# -*- coding: utf-8 -*-
"""
train_lora.py — QLoRA fine-tune of Qwen3.5-4B on the mixed Hebrew+English Torah dataset.
─────────────────────────────────────────────────────────────────────────────
נייד: רץ זהה ב-Colab / Kaggle / Lightning (GPU יחיד ~16GB) וגם ב-Nebius.
משתמש ב-Unsloth + QLoRA 4-bit — הדרך היחידה שמכניסה 4B בנוחות ל-16GB ומהירה.

התקנה (תא ראשון במחברת, פעם אחת):
    pip install -U "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
    pip install -U trl peft accelerate bitsandbytes datasets

הרצה:
    python scripts/train_lora.py
    # או עם שינויים:
    python scripts/train_lora.py --model Qwen/Qwen3.5-4B --epochs 1 --max_seq 2048

הערה ל-Qwen3.5 (מודל חדש): אם Unsloth עדיין לא מזהה אותו, עדכן את Unsloth
לגרסה האחרונה. ה-chat template נמשך אוטומטית מהטוקנייזר — אין צורך לכתוב אותו.
"""

import argparse
import json
import os

# ─────────────────────────────────────────────
# ארגומנטים — ברירות מחדל מכוונות ל-T4 16GB
# ─────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model",   default="unsloth/Qwen3-4B",
                   help="HF id של ה-base (unsloth/Qwen3-4B = יציב ב-fp16 על T4).")
    p.add_argument("--train",   default="data/processed/torah_mixed_train.jsonl")
    p.add_argument("--val",     default="data/processed/torah_mixed_val.jsonl")
    p.add_argument("--out",     default="outputs/chavruta-qwen35-4b-lora")
    p.add_argument("--max_seq", type=int,   default=2048)   # מכסה ~97.5% מהדוגמאות
    p.add_argument("--epochs",  type=float, default=1.0)
    p.add_argument("--bs",      type=int,   default=2)      # per-device
    p.add_argument("--grad_accum", type=int, default=4)     # effective batch = bs*grad_accum = 8
    p.add_argument("--lr",      type=float, default=2e-4)
    p.add_argument("--lora_r",  type=int,   default=16)
    p.add_argument("--lora_alpha", type=int, default=16)
    p.add_argument("--warmup_ratio", type=float, default=0.03)
    p.add_argument("--eval_steps",  type=int, default=200)
    p.add_argument("--save_steps",  type=int, default=200)
    p.add_argument("--seed",    type=int,   default=42)
    p.add_argument("--save_merged", action="store_true",
                   help="שמור גם משקלים ממוזגים (16-bit) להעלאה/הסקה.")
    return p.parse_args()


def main():
    args = parse_args()

    # Unsloth חייב להיות מיובא לפני transformers/trl כדי שה-patch יחול
    from unsloth import FastLanguageModel, is_bfloat16_supported
    from unsloth.chat_templates import train_on_responses_only
    from datasets import load_dataset
    from trl import SFTTrainer, SFTConfig

    # ── 1. טעינת מודל + טוקנייזר ב-4bit ──────────
    print(f"⏳ loading {args.model} (4-bit QLoRA) ...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name      = args.model,
        max_seq_length  = args.max_seq,
        load_in_4bit    = True,
        dtype           = None,   # אוטומטי: bf16 על Ampere+, אחרת fp16
    )

    # ── 2. עטיפת LoRA (adapters) ──────────────────
    model = FastLanguageModel.get_peft_model(
        model,
        r              = args.lora_r,
        lora_alpha     = args.lora_alpha,
        lora_dropout   = 0.0,            # Unsloth ממוטב ל-0
        bias           = "none",
        target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                          "gate_proj", "up_proj", "down_proj"],
        use_gradient_checkpointing = "unsloth",   # חוסך VRAM משמעותית
        random_state   = args.seed,
    )

    # ── 3. פורמט הדאטה דרך ה-chat template של המודל ─
    def fmt(batch):
        texts = [
            tokenizer.apply_chat_template(m, tokenize=False, add_generation_prompt=False)
            for m in batch["messages"]
        ]
        return {"text": texts}

    train_ds = load_dataset("json", data_files=args.train, split="train").map(
        fmt, batched=True, remove_columns=["messages"])
    val_ds = load_dataset("json", data_files=args.val, split="train").map(
        fmt, batched=True, remove_columns=["messages"])
    print(f"📊 train={len(train_ds):,}  val={len(val_ds):,}")

    # ── 4. הגדרת אימון ────────────────────────────
    cfg = SFTConfig(
        output_dir              = args.out,
        per_device_train_batch_size = args.bs,
        per_device_eval_batch_size  = args.bs,
        gradient_accumulation_steps = args.grad_accum,
        num_train_epochs        = args.epochs,
        learning_rate           = args.lr,
        warmup_ratio            = args.warmup_ratio,
        lr_scheduler_type       = "cosine",
        optim                   = "adamw_8bit",   # חוסך VRAM
        weight_decay            = 0.01,
        max_length              = args.max_seq,   # TRL החדש: max_length (לא max_seq_length)
        padding_free            = False,          # TRL מפעיל padding_free כברירת מחדל — מכבים כדי שהחיתוך ל-max_length ייאכף
        dataset_text_field      = "text",
        packing                 = False,          # שלא יערבב דוגמאות
        bf16                    = is_bfloat16_supported(),
        fp16                    = not is_bfloat16_supported(),
        logging_steps           = 10,
        eval_strategy           = "steps",
        eval_steps              = args.eval_steps,
        save_strategy           = "steps",
        save_steps              = args.save_steps,
        save_total_limit        = 3,
        report_to               = "none",
        seed                    = args.seed,
    )

    trainer = SFTTrainer(
        model           = model,
        tokenizer       = tokenizer,
        train_dataset   = train_ds,
        eval_dataset    = val_ds,
        args            = cfg,
    )

    # ── 5. אמן רק על תשובת ה-assistant (masking) ──
    # מסמני Qwen (ChatML). אם Qwen3.5 משנה תבנית — התאם כאן.
    trainer = train_on_responses_only(
        trainer,
        instruction_part = "<|im_start|>user\n",
        response_part    = "<|im_start|>assistant\n",
    )

    # ── 6. אימון ──────────────────────────────────
    print("🚀 training ...")
    stats = trainer.train()
    print("✅ done:", stats.metrics if hasattr(stats, "metrics") else stats)

    # ── 7. שמירה ──────────────────────────────────
    os.makedirs(args.out, exist_ok=True)
    model.save_pretrained(args.out)             # adapter בלבד (קטן)
    tokenizer.save_pretrained(args.out)
    print(f"💾 LoRA adapter saved → {args.out}")

    if args.save_merged:
        merged = f"{args.out}-merged-16bit"
        model.save_pretrained_merged(merged, tokenizer, save_method="merged_16bit")
        print(f"💾 merged 16-bit model saved → {merged}")


if __name__ == "__main__":
    main()
