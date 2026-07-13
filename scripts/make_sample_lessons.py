# -*- coding: utf-8 -*-
"""Generate one live lesson per template and save readable Markdown + raw JSON.

    python scripts/make_sample_lessons.py        # backend must be up on :8080

Output → sample_lessons/<slug>.md  and  <slug>.json
"""
import json
import time
import urllib.request
from pathlib import Path

API = "http://localhost:8080/query"
OUT = Path("sample_lessons")
OUT.mkdir(exist_ok=True)

# One topic per template (the selected template is reported per lesson — it is chosen
# automatically by topic↔when_to_use similarity, so it may differ from the intent).
TOPICS = [
    ("talmudic_sugya",    "שניים אוחזין בטלית"),
    ("machloket_rishonim", "מחלוקת הראשונים בפירוש הפסוק הראשון בתורה"),
    ("parsha_iyun",        "עיון בפרשת בראשית ובריאת העולם"),
    ("machshava_mussar",   "שיעור במוסר על מידת הענווה"),
]

ROLE_HE = {"opening": "פתיחה", "branch": "ענף", "convergence": "התכנסות"}


def ask(question, retries=3):
    body = json.dumps({"question": question, "intent": "lesson", "lang": "he"}).encode("utf-8")
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=1500) as r:  # big sugya may take long — fine
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:                                    # transient local-Qdrant 500/timeout
            last = e
            print(f"  retry ({type(e).__name__}) …", flush=True)
            time.sleep(8 * (attempt + 1))
    raise last


def _body(text):
    # drop the internal "[label] Ref daf:seg" header line (may hold a pre-fix daf label)
    if text.startswith("[") and "\n" in text:
        return text.split("\n", 1)[1]
    return text


def cite_line(c):
    ref = c.get("ref", "")
    comm = f" · {c['commentator']}" if c.get("commentator") else ""
    he = _body((c.get("text_he") or "").strip()).strip()
    dl = c.get("deep_link") or ""
    link = f"  [↗]({dl})" if dl else ""
    return f"- **{ref}**{comm}{link}\n  > {he}"


def to_md(intended, question, d):
    lp = d.get("lesson_plan") or {}
    lines = [f"# {question}", ""]
    lines.append(f"- **תבנית מבוקשת:** `{intended}`")
    lines.append(f"- **תבנית שנבחרה:** `{lp.get('template_id')}`")
    lines.append(f"- **סוגיא פתוחה:** {lp.get('is_open')}  ·  **מעוגן:** {d.get('grounded')}  "
                 f"·  **מקטעים:** {len(lp.get('sections') or [])}")
    if d.get("caveats"):
        lines.append(f"- **הערות:** {'; '.join(d['caveats'])}")
    lines += ["", "## קשת השיעור", ""]
    for s in lp.get("sections") or []:
        role = ROLE_HE.get(s.get("role"), s.get("role"))
        refs = ", ".join(s.get("source_refs") or [])
        lines.append(f"### [{role}] {s.get('heading')}")
        lines.append(f"*מקורות:* {refs}")
        lines.append("")
        for c in s.get("citations") or []:
            lines.append(cite_line(c))
        lines.append("")
    lines += ["## התשובה המלאה", "", (d.get("answer") or "").strip(), ""]
    cites = d.get("citations") or []
    if cites:
        lines += ["## כל המקורות שצוטטו", ""]
        lines += [cite_line(c) for c in cites]
    return "\n".join(lines) + "\n"


def rerender():
    """Re-render the .md files from already-saved .json (instant, no backend)."""
    index = ["# שיעורים לדוגמה (אחד לכל תבנית)", ""]
    for intended, q in TOPICS:
        jf = OUT / f"{intended}.json"
        if not jf.exists():
            continue
        d = json.loads(jf.read_text(encoding="utf-8"))
        (OUT / f"{intended}.md").write_text(to_md(intended, q, d), encoding="utf-8")
        lp = d.get("lesson_plan") or {}
        index.append(f"- [{q}]({intended}.md) — תבנית `{lp.get('template_id')}`, "
                     f"{len(lp.get('sections') or [])} מקטעים")
    (OUT / "README.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    print(f"✅ re-rendered {OUT}/ from saved JSON")


def main():
    import sys
    if "--rerender" in sys.argv:
        rerender()
        return
    index = ["# שיעורים לדוגמה (אחד לכל תבנית)", ""]
    for intended, q in TOPICS:
        slug = intended
        print(f"[{intended}] {q} …", flush=True)
        try:
            d = ask(q)
        except Exception as e:
            print(f"  FAILED: {e}", flush=True)
            continue
        (OUT / f"{slug}.json").write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / f"{slug}.md").write_text(to_md(intended, q, d), encoding="utf-8")
        lp = d.get("lesson_plan") or {}
        print(f"  -> template={lp.get('template_id')} sections={len(lp.get('sections') or [])} "
              f"grounded={d.get('grounded')} chars={len(d.get('answer') or '')}", flush=True)
        index.append(f"- [{q}]({slug}.md) — תבנית `{lp.get('template_id')}`, "
                     f"{len(lp.get('sections') or [])} מקטעים")
    (OUT / "README.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    print(f"\n✅ saved to {OUT}/", flush=True)


if __name__ == "__main__":
    main()
