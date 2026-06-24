# -*- coding: utf-8 -*-
"""Example שו"ת question per template + verify each selects its intended template.

Selection is checked twice: within the responsa set alone, and within the COMBINED set
(lesson + responsa templates) — so we confirm a שו"ת question prefers a responsa template
even when both sets share one index. Saves a readable doc to sample_lessons/shut_examples.md.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chavruta.embedding.bge_m3 import BgeM3Embedding
from chavruta.lessons.templates import SHUT_PATH, TemplateIndex, load_templates

# One representative question per responsa template.
QUESTIONS = {
    "shut_pesak":     "מבקש הוראה למעשה: כיצד עליי לנהוג בברכת הגומל לאחר טיסה ארוכה?",
    "shut_tzdadim":   "יש בזה צד היתר וצד איסור — האם מותר לסחוט לימון לתוך תה בשבת? מה סברות המתירים ומה סברות האוסרים?",
    "shut_birur_din": "מהו גדרו של 'דבר שאינו מתכוון' בהלכות שבת, ומה מקורו? (בירור הגדרה)",
}

emb = BgeM3Embedding(model_id="BAAI/bge-m3", device="cpu", use_sparse=False)
shut = load_templates(SHUT_PATH)
combined = load_templates() + shut
shut_idx = TemplateIndex(shut, emb)
all_idx = TemplateIndex(combined, emb)
by_id = {t.template_id: t for t in combined}

out = ["# שאלות שו\"ת לדוגמה — אחת לכל תבנית", ""]
ok = True
for tid, q in QUESTIONS.items():
    s = shut_idx.select(q).template_id
    a = all_idx.select(q).template_id
    hit = "✓" if (s == tid and a == tid) else "✗"
    if s != tid or a != tid:
        ok = False
    print(f"{hit} {tid}: shut-only={s} | combined={a}", flush=True)
    t = by_id[tid]
    out += [f"## {t.name_he}  (`{tid}`)", "",
            f"**שאלה לדוגמה:** {q}", "",
            f"- בחירת תבנית (סט שו\"ת בלבד): `{s}`  ·  (סט משולב שיעור+שו\"ת): `{a}`",
            "- **מהלך התשובה הצפוי (שלד התבנית):**"]
    for st in t.stages:
        role = {"opening": "פתיחה", "branch": "ענף", "convergence": "הכרעה"}.get(st.key, st.key)
        out.append(f"  {len(out) and ''}1. [{role}] {st.title_he}  — _{', '.join(st.source_kinds)}_")
    out.append("")

dst = Path("sample_lessons"); dst.mkdir(exist_ok=True)
(dst / "shut_examples.md").write_text("\n".join(out), encoding="utf-8")
print(f"\n{'ALL SELECTED CORRECTLY' if ok else 'SOME MISMATCH'} → sample_lessons/shut_examples.md")
