# אימון LoRA — מדריך הרצה לכל פלטפורמה

מודל בסיס: **Qwen3.5-4B** · שיטה: **QLoRA 4-bit (Unsloth)** · דאטה: `torah_mixed_train.jsonl` (87,151) + `torah_mixed_val.jsonl` (4,493)

> אסטרטגיה: להריץ קודם על החינמיים (Colab/Kaggle/Lightning, GPU יחיד), ולשמור את נביוס + ה-$100 לריצה הגדולה/הסופית.

---

## התקנה (תא ראשון, פעם אחת בכל סביבה)
```bash
pip install -U "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
pip install -U trl peft accelerate bitsandbytes datasets
```

## הרצה בסיסית (GPU יחיד 16GB — Colab / Kaggle / Lightning)
```bash
python scripts/train_lora.py --model Qwen/Qwen3.5-4B --epochs 1
```
ברירות המחדל (`bs=2`, `grad_accum=4` → batch אפקטיבי 8, `max_seq=2048`) מכוונות ל-T4 16GB.
אם נגמר ה-VRAM (OOM): הורד `--max_seq 1024` או `--bs 1 --grad_accum 8`.

---

## פלט (per-platform)

| פלטפורמה | GPU טיפוסי | הערות |
|----------|-----------|-------|
| **Colab (free)** | T4 16GB | מתנתק אחרי ~3–4 ש'. שמור checkpoints ל-Google Drive (`--out /content/drive/...`). |
| **Kaggle** | T4×2 או P100 16GB | 30 ש'/שבוע GPU. הרץ על GPU יחיד מהסקריפט (לא צריך multi-GPU). |
| **Lightning AI** | T4/A10 (free credits) | זהה ל-Colab. |
| **Nebius** | A100/H100 ×1–16 | לריצה הסופית — ראה למטה. |

**העלאת הדאטה:** העלה את שני קבצי ה-`.jsonl` מ-`data/processed/` לסביבה, או clone של הריפו.

---

## נביוס — ריצה גדולה (תקציב $100)
על GPU יחיד חזק (A100/H100) פשוט הגדל batch ו/או הוסף epoch:
```bash
python scripts/train_lora.py --model Qwen/Qwen3.5-4B \
  --bs 8 --grad_accum 2 --max_seq 2048 --epochs 2 --save_merged
```
ל-multi-GPU (8/16) — עטוף ב-accelerate (data-parallel):
```bash
accelerate launch --multi_gpu --num_processes 8 scripts/train_lora.py --bs 8 --grad_accum 1
```
> **שיקול תקציב:** H100 בודד ב~$2–3/שעה. אפוק אחד של 4B QLoRA ≈ כמה שעות → הריצה הסופית
> בקלות נכנסת ב-$100. כדאי לעשות sweep קצר בחינם (Colab) למצוא LR/epochs, ואז ריצה אחת נקייה בנביוס.

---

## אומדן זמן (epoch 1, ~10,900 steps)
- T4 (Colab/Kaggle): ~2–4 שעות
- A100: ~40–70 דקות
- H100: ~25–45 דקות

## אחרי האימון
- נשמר **adapter** בלבד ל-`outputs/...-lora` (קטן, כמה MB).
- עם `--save_merged` → גם מודל ממוזג 16-bit להסקה/העלאה ל-HF.
- בדיקה מהירה: טען base + adapter, שאל שאלה עברית ושאלה אנגלית, ודא ש**עונה בשפת השאלה** (זה מה ש-`train_on_responses_only` + הדאטה החד-לשוני אמורים לקבע).

## נקודות תשומת לב
- **Qwen3.5 חדש** — אם Unsloth לא מזהה את ה-id, עדכן Unsloth לאחרון. אם תבנית ה-chat שונה
  מ-ChatML, התאם את המסמנים ב-`train_on_responses_only` בתוך [train_lora.py](train_lora.py).
- הסקריפט **לא נבדק בהרצה** כאן (אין GPU מקומי) — הלוגיקה סטנדרטית, אך הריצה הראשונה
  על Colab תאמת אותה. אם תיתקל בשגיאה — שלח לי אותה ואתקן.
