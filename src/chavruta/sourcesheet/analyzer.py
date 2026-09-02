"""Source Sheet Companion Analyzer & Synthesizer (Spec 008 Phase 3).

Grounded sugya flow analysis, XML-isolated source prompt construction,
Mermaid flowchart generation, comparative opinion tables, tiered chavruta
questions, and multi-format export (Markdown, Word .docx).
"""

from __future__ import annotations

import io
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from chavruta.corpus.schema import Citation
from chavruta.sourcesheet.parser import ParsedSourceItem

_log = logging.getLogger("chavruta.sourcesheet.analyzer")

# ── Verification Statuses (Principle I) ──────────────────────────────────────

STATUS_VERIFIED_CORPUS = "VERIFIED_CORPUS"
STATUS_USER_PROVIDED = "USER_PROVIDED"
STATUS_MISSING_REF = "MISSING_REF"

STATUS_LABELS_HE = {
    STATUS_VERIFIED_CORPUS: "מאומת ומורחב מהמאגר",
    STATUS_USER_PROVIDED: "מקור מדף המשתמש — לא אומת מול מאגר חברותא",
    STATUS_MISSING_REF: "מראה מקום שלא נמצא במאגר (חסר טקסט)",
}


@dataclass
class SourceSection:
    index: int
    title: str
    ref: str | None
    status: str
    role_tag: str
    source_snippet: str
    expanded_context: str | None = None
    plain_explanation: str = ""
    diyuk: str | None = None
    difficult_words: dict[str, str] = field(default_factory=dict)
    author_note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CompanionGuide:
    title: str
    topic: str
    core_inquiry: str
    flowchart_mermaid: str
    sections: list[SourceSection]
    opinion_table: list[dict[str, str]]
    chavruta_questions: dict[str, list[str]]  # peshat, comparison, sevara
    summary: str
    citations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "topic": self.topic,
            "core_inquiry": self.core_inquiry,
            "flowchart_mermaid": self.flowchart_mermaid,
            "sections": [s.to_dict() for s in self.sections],
            "opinion_table": self.opinion_table,
            "chavruta_questions": self.chavruta_questions,
            "summary": self.summary,
            "citations": self.citations,
        }

    def to_markdown(self) -> str:
        """Produce a complete, beautifully-formatted Markdown companion guide."""
        md = []
        md.append(f"# חוברת ליווי לדף מקורות: {self.title or self.topic}\n")
        md.append(f"> **נושא הסוגיה:** {self.topic}\n")
        md.append("## שאלת היסוד וציר החקירה (The Core Inquiry)")
        md.append(f"{self.core_inquiry}\n")

        if self.flowchart_mermaid:
            md.append("## מפת מהלך הסוגיה (Thematic Flowchart)")
            md.append("```mermaid")
            md.append(self.flowchart_mermaid)
            md.append("```\n")

        md.append("## ביאור מקורות הדף (מקור-אחר-מקור)\n")
        for s in self.sections:
            badge = STATUS_LABELS_HE.get(s.status, s.status)
            md.append(f"### מקור {s.index}: {s.title} `{s.role_tag}`")
            md.append(f"> **סטטוס מקור:** *[{badge}]*")
            if s.ref:
                md.append(f"> **מראה מקום:** `{s.ref}`")
            md.append("")

            if s.status == STATUS_MISSING_REF:
                md.append(
                    "> ⚠️ **הערת מערכת:** מראה מקום זה אינו מצוטט בדף ואינו קיים במאגר. "
                    "לא ניתן לבאר ללא ציטוט הטקסט — באפשרותך להזין את לשונו בצ'אט.\n"
                )
                continue

            md.append(f"**לשון המקור:**\n> {s.source_snippet}\n")
            if s.plain_explanation:
                md.append(f"**ביאור הפשט והמהלך:**\n{s.plain_explanation}\n")
            if s.diyuk:
                md.append(f"**נקודת הדיוק (דיוק הלשון):**\n*{s.diyuk}*\n")
            if s.difficult_words:
                words_str = ", ".join(f"**{k}**: {v}" for k, v in s.difficult_words.items())
                md.append(f"**מילים מנחות וביאורי מילים:** {words_str}\n")
            if s.author_note:
                md.append(f"💡 **הערת עורך הדף:** `{s.author_note}`\n")
            md.append("---\n")

        if self.opinion_table:
            md.append("## טבלת השוואת שיטות ומחלוקות")
            md.append("| שיטה / בעל הדעה | סברת היסוד | הראיה / המקור | נפקא מינה |")
            md.append("|---|---|---|---|")
            for row in self.opinion_table:
                opinion = row.get("opinion", "")
                reason = row.get("reason", "")
                proof = row.get("proof", "")
                nafka = row.get("nafka_mina", "")
                md.append(f"| {opinion} | {reason} | {proof} | {nafka} |")
            md.append("")

        if self.chavruta_questions:
            md.append("## שאלות לעיון וחזרת החברותא")
            if self.chavruta_questions.get("peshat"):
                md.append("### 1. רמת פשט והבנת המקורות:")
                for q in self.chavruta_questions["peshat"]:
                    md.append(f"- {q}")
            if self.chavruta_questions.get("comparison"):
                md.append("\n### 2. רמת השוואה ודיוק שיטות:")
                for q in self.chavruta_questions["comparison"]:
                    md.append(f"- {q}")
            if self.chavruta_questions.get("sevara"):
                md.append("\n### 3. רמת סברא והעמקה מושגית:")
                for q in self.chavruta_questions["sevara"]:
                    md.append(f"- {q}")
            md.append("")

        if self.summary:
            md.append("## סיכום ומסקנות הסוגיה")
            md.append(f"{self.summary}\n")

        return "\n".join(md)

    def to_docx_bytes(self) -> bytes:
        """Produce a styled Word .docx file with RTL tables and headers."""
        try:
            import docx
            from docx.enum.text import WD_ALIGN_PARAGRAPH

            doc = docx.Document()
            # Title
            title_p = doc.add_paragraph()
            title_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            run = title_p.add_run(f"חוברת ליווי לדף מקורות: {self.title or self.topic}")
            run.bold = True
            run.font.size = docx.shared.Pt(18)

            # Core inquiry
            doc.add_heading("שאלת היסוד ומהלך הסוגיה", level=1)
            p = doc.add_paragraph(self.core_inquiry)
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT

            # Sections
            doc.add_heading("ביאור מקורות הדף", level=1)
            for s in self.sections:
                doc.add_heading(f"מקור {s.index}: {s.title} ({s.role_tag})", level=2)
                badge = STATUS_LABELS_HE.get(s.status, s.status)
                doc.add_paragraph(f"סטטוס מקור: {badge}")
                if s.status != STATUS_MISSING_REF:
                    doc.add_paragraph(f"לשון המקור: {s.source_snippet}")
                    if s.plain_explanation:
                        doc.add_paragraph(f"ביאור: {s.plain_explanation}")
                    if s.diyuk:
                        doc.add_paragraph(f"נקודת הדיוק: {s.diyuk}")

            # Opinion table
            if self.opinion_table:
                doc.add_heading("טבלת השוואת שיטות", level=1)
                table = doc.add_table(rows=1, cols=4)
                hdr_cells = table.rows[0].cells
                hdr_cells[0].text = "שיטה / בעל הדעה"
                hdr_cells[1].text = "סברת היסוד"
                hdr_cells[2].text = "הראיה / המקור"
                hdr_cells[3].text = "נפקא מינה"
                for row in self.opinion_table:
                    row_cells = table.add_row().cells
                    row_cells[0].text = row.get("opinion", "")
                    row_cells[1].text = row.get("reason", "")
                    row_cells[2].text = row.get("proof", "")
                    row_cells[3].text = row.get("nafka_mina", "")

            # Chavruta questions
            if self.chavruta_questions:
                doc.add_heading("שאלות לעיון בחברותא", level=1)
                for level_name, qs in self.chavruta_questions.items():
                    for q in qs:
                        doc.add_paragraph(f"• {q}")

            buf = io.BytesIO()
            doc.save(buf)
            return buf.getvalue()
        except Exception as exc:
            _log.warning("docx generation failed: %s", exc)
            return b""


# ── XML-Isolated Context Construction (Principle I) ──────────────────────────

def build_sourcesheet_prompt_context(
    items: list[ParsedSourceItem],
    corpus_lookup: dict[str, str] | None = None,
) -> str:
    """Build strictly-isolated XML source blocks to prevent parametric hallucinations."""
    blocks = []
    lookup = corpus_lookup or {}

    for item in items:
        source_id = f"S{item.index}"
        ref = item.ref or "None"
        canonical = item.canonical_sefaria_ref or ""
        corpus_text = lookup.get(canonical) or lookup.get(ref)

        has_substantive_body = bool(
            item.cleaned_text
            and item.cleaned_text.strip() != item.header.strip()
            and len(item.cleaned_text.strip()) > 5
        )
        if corpus_text:
            status = STATUS_VERIFIED_CORPUS
        elif has_substantive_body:
            status = STATUS_USER_PROVIDED
        else:
            status = STATUS_MISSING_REF

        block = [f'<source id="{source_id}" status="{status}" ref="{ref}">']
        block.append(f"  <header>{item.header}</header>")
        if item.dibur_hamatchil:
            block.append(f"  <dibur_hamatchil>{item.dibur_hamatchil}</dibur_hamatchil>")
        if item.author_note_text:
            block.append(f"  <author_annotation>{item.author_note_text}</author_annotation>")
        if corpus_text:
            block.append(f"  <corpus_verified_text>{corpus_text}</corpus_verified_text>")
        elif status == STATUS_USER_PROVIDED:
            block.append(f"  <user_provided_text>{item.cleaned_text}</user_provided_text>")
        else:
            block.append("  <instruction>UNINDEXED BARE REF. DO NOT HALLUCINATE TEXT.</instruction>")
        block.append("</source>")
        blocks.append("\n".join(block))

    return "\n\n".join(blocks)


# ── Structured Sugya Synthesis Engine ────────────────────────────────────────

def _clean_topic_text(text: str) -> str:
    """Sanitize and strip leaked system instructions or imperative query prefixes from topic."""
    if not text:
        return ""
    # Strip system prompt leakage
    cleaned = re.sub(r"\(לא מהמאגר[^\)]*\)", "", text)
    cleaned = re.sub(r"\(not from the corpus[^\)]*\)", "", cleaned)
    cleaned = re.sub(r"##\s+(?:מקורות שצירף המשתמש|Sources the user attached)[^\n]*", "", cleaned)
    cleaned = re.sub(r"###\s+(?:מקור|Source)\s*\d*", "", cleaned)
    # Strip imperative query prefixes
    imperative_prefixes = [
        r"^(?:תסכם|סכם|באר|תבאר|הסבר|תסביר|נתח|תנתח|בנה|תבנה|הצג|תציג)\s+(?:לי\s+)?(?:את\s+)?(?:כל\s+)?(?:המהלך\s+של\s+)?(?:דף\s+המקורות|הסוגיה|המקורות|הדף)?(?:\s*[:—–-])?\s*",
        r"^(?:מה\s+הוא|מהו|מהם|כיצד|איך)\s+",
    ]
    for pat in imperative_prefixes:
        cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned.strip().strip(":—–- ")


def _synthesize_with_llm(
    items: list[ParsedSourceItem],
    topic_hint: str,
    corpus_lookup: dict[str, str],
    llm: Any,
    lang: str,
    user_instruction: str = "",
) -> CompanionGuide | None:
    """Invoke the LLM to perform deep Torah synthesis of the source sheet."""
    sources_xml = build_sourcesheet_prompt_context(items, corpus_lookup)
    prompt = f"""אתה תלמיד חכם מובהק, מגיד שיעור ועורך תורני מומחה במערכת 'חברותא AI'.
לפניך דף מקורות תורני שחולץ לתוך מקטעי XML (מקורות מאומתים מהמאגר או טקסטים מדף המשתמש).
עליך לנתח את הדף ברמה למדנית ופדגוגית גבוהה, ולבנות חוברת ליווי מקיפה למהלך הסוגיה.

הנחיות חמורות (Principle I):
- התבסס אך ורק על המקורות המופיעים ב-XML למטה. אל תמציא מקורות או מובאות שלא ניתנו.
- אם מופיע מקור ללא טקסט (UNINDEXED BARE REF), ציין שהוא מראה מקום בלבד ואל תבדה את תוכנו.
- זהה את נושא הסוגיה האמיתי (למשל: "מצות תלמוד תורה וגדריה", "ייאוש שלא מדעת", "קניין כסף"). אל תשתמש בהוראות משתמש או במחרוזות מערכת כנושא.

החזר פלט מובנה בפורמט JSON בלבד (עטוף ב-```json ... ``` או JSON ישיר בלבד, ללא מלל נוסף לפני או אחרי):
{{
  "topic": "נושא הסוגיה המרכזי והמדויק (2-5 מילים)",
  "core_inquiry": "שאלת היסוד, ציר החקירה והסברא העומדת במוקד הסוגיה (2-4 משפטים)",
  "summary": "סיכום מקיף, תמציתי ובהיר של מהלך הסוגיה, השתלשלות השיטות והמסקנה (3-5 פסקאות)",
  "sections": [
    {{
      "index": 1,
      "title": "כותרת המקור (למשל: בבא מציעא דף כ\"א ע\"א / רמב\"ם הלכות ת\"ת)",
      "role_tag": "מקור יסוד / עובדא דש\"ס | קושיא / דיוק | חידוש / יסוד הסברא | ראיה / סייעתא | שיטה חולקת | הכרעה הלכתית",
      "plain_explanation": "ביאור תמציתי ומאיר עיניים של המקור, תוך הדגשת מקומו במהלך",
      "diyuk": "דיוק בלשון המקור או דיבור המתחיל (אם ישנו)",
      "difficult_words": {{"מילה קשה": "פירושה"}}
    }}
  ],
  "opinion_table": [
    {{
      "opinion": "שם השיטה / בעל הדעה",
      "reason": "טעם וסברא מרכזית",
      "proof": "מקור וראיה",
      "nafka_mina": "נפקא מינה להלכה או למעשה"
    }}
  ],
  "chavruta_questions": {{
    "peshat": ["שאלת פשט והבנה 1", "שאלת פשט והבנה 2"],
    "comparison": ["שאלת השוואת שיטות 1", "שאלת השוואת שיטות 2"],
    "sevara": ["שאלת סברא, חקירה ולמדנות 1", "שאלת סברא ולמדנות 2"]
  }},
  "flowchart_mermaid": "flowchart TD\\n    A[שאלת היסוד] --> B[מקור 1]\\n    B --> C[מקור 2]"
}}

מקורות הדף לעיון:
{sources_xml}
"""
    try:
        response_text = ""
        if hasattr(llm, "generate"):
            res = llm.generate(prompt, lang="he", max_tokens=3500, temperature=0.2)
            response_text = res.text if hasattr(res, "text") else str(res)
        elif hasattr(llm, "complete"):
            response_text = str(llm.complete(prompt))

        if not response_text:
            return None

        # Extract JSON block
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
        raw_json = json_match.group(1) if json_match else response_text.strip()
        if not json_match and "{" in raw_json and "}" in raw_json:
            raw_json = raw_json[raw_json.find("{"):raw_json.rfind("}") + 1]

        # Convert unescaped Hebrew acronym quotes (e.g. רמב"ם -> רמב״ם) to avoid invalid JSON syntax
        raw_json = re.sub(r'(?<=[\u0590-\u05FF])"(?=[\u0590-\u05FF])', '״', raw_json)

        data = json.loads(raw_json)
        raw_topic = data.get("topic") or topic_hint or (items[0].header if items else "סוגיה תורנית")
        topic = _clean_topic_text(raw_topic) or "סוגיה תורנית"
        core_inquiry = data.get("core_inquiry") or f"בירור יסודות וגדרי {topic}."
        summary = data.get("summary") or ""

        llm_sections_data = {s.get("index", idx + 1): s for idx, s in enumerate(data.get("sections", []))}
        sections: list[SourceSection] = []
        citations: list[str] = []

        for item in items:
            sec_data = llm_sections_data.get(item.index, {})
            ref = item.ref or item.header
            canonical = item.canonical_sefaria_ref or ""
            corpus_text = corpus_lookup.get(canonical) or corpus_lookup.get(ref)
            has_body = bool(
                item.cleaned_text
                and item.cleaned_text.strip() != item.header.strip()
                and len(item.cleaned_text.strip()) > 5
            )

            if corpus_text:
                status = STATUS_VERIFIED_CORPUS
                snippet = corpus_text[:300] + ("…" if len(corpus_text) > 300 else "")
                citations.append(ref)
            elif has_body:
                status = STATUS_USER_PROVIDED
                snippet = item.cleaned_text
            else:
                status = STATUS_MISSING_REF
                snippet = "(טקסט אינו קיים בדף ואינו במאגר)"

            raw_title = sec_data.get("title") or item.header or ref or f"מקור {item.index}"
            title = _clean_topic_text(raw_title) or (ref or f"מקור {item.index}")
            role = sec_data.get("role_tag") or "מקור"
            explanation = sec_data.get("plain_explanation") or f"ביאור מקור {item.index} במסגרת מהלך הסוגיה."
            diyuk = sec_data.get("diyuk") or (item.dibur_hamatchil and f'ד"ה "{item.dibur_hamatchil}"')

            sec = SourceSection(
                index=item.index,
                title=title,
                ref=ref if ref != "None" else None,
                status=status,
                role_tag=role,
                source_snippet=snippet,
                expanded_context=corpus_text,
                plain_explanation=explanation,
                diyuk=diyuk,
                difficult_words=sec_data.get("difficult_words") or {},
                author_note=item.author_note_text,
            )
            sections.append(sec)

        flowchart = data.get("flowchart_mermaid") or ""
        opinion_table = data.get("opinion_table") or []
        chavruta_questions = data.get("chavruta_questions") or {}

        return CompanionGuide(
            title=f"מהלך הסוגיה — {topic}",
            topic=topic,
            core_inquiry=core_inquiry,
            flowchart_mermaid=flowchart,
            sections=sections,
            opinion_table=opinion_table,
            chavruta_questions=chavruta_questions,
            summary=summary,
            citations=citations,
        )
    except Exception as exc:
        _log.warning("sourcesheet LLM synthesis failed, falling back to deterministic: %s", exc)
        return None


# ── Structured Sugya Synthesis Engine ────────────────────────────────────────

def analyze_source_sheet(
    items: list[ParsedSourceItem],
    topic_hint: str = "",
    corpus_lookup: dict[str, str] | None = None,
    llm=None,
    lang: str = "he",
    user_instruction: str = "",
) -> CompanionGuide:
    """Synthesize a complete Source Sheet Companion Guide.

    Uses LLM for deep Torah analysis when available, with deterministic fallback.
    """
    if not items:
        return CompanionGuide(
            title="דף מקורות ריק",
            topic="ללא מקורות",
            core_inquiry="לא זוהו מקורות בדף שהועלה.",
            flowchart_mermaid="",
            sections=[],
            opinion_table=[],
            chavruta_questions={},
            summary="לא זוהו מקורות.",
        )

    lookup = corpus_lookup or {}

    # Try LLM synthesis first if LLM is provided
    if llm is not None:
        guide = _synthesize_with_llm(
            items=items,
            topic_hint=topic_hint,
            corpus_lookup=lookup,
            llm=llm,
            lang=lang,
            user_instruction=user_instruction,
        )
        if guide is not None:
            return guide

    # Deterministic fallback
    sections: list[SourceSection] = []
    citations: list[str] = []

    role_cycle = [
        "מקור יסוד / עובדא דש\"ס",
        "קושיא / דיוק",
        "חידוש / יסוד הסברא",
        "ראיה / סייעתא",
        "שיטה חולקת",
        "הכרעה הלכתית",
    ]

    for idx, item in enumerate(items):
        ref = item.ref or item.header
        canonical = item.canonical_sefaria_ref or ""
        corpus_text = lookup.get(canonical) or lookup.get(ref)

        has_substantive_body = bool(
            item.cleaned_text
            and item.cleaned_text.strip() != item.header.strip()
            and len(item.cleaned_text.strip()) > 5
        )
        if corpus_text:
            status = STATUS_VERIFIED_CORPUS
            snippet = corpus_text[:300] + ("…" if len(corpus_text) > 300 else "")
            citations.append(ref)
        elif has_substantive_body:
            status = STATUS_USER_PROVIDED
            snippet = item.cleaned_text
        else:
            status = STATUS_MISSING_REF
            snippet = "(טקסט אינו קיים בדף ואינו במאגר)"

        role = role_cycle[idx % len(role_cycle)]
        raw_title = item.header if item.header and len(item.header) < 60 else (ref or f"מקור {item.index}")
        title = _clean_topic_text(raw_title) or (ref or f"מקור {item.index}")

        sec = SourceSection(
            index=item.index,
            title=title,
            ref=ref if ref != "None" else None,
            status=status,
            role_tag=role,
            source_snippet=snippet,
            expanded_context=corpus_text,
            plain_explanation=f"ביאור מקור {item.index} במסגרת מהלך הסוגיה.",
            diyuk=item.dibur_hamatchil and f'עומד על הדיבור המתחיל "{item.dibur_hamatchil}"',
            author_note=item.author_note_text,
        )
        sections.append(sec)

    cleaned_topic = _clean_topic_text(topic_hint)
    first_header = _clean_topic_text(items[0].header) if items else ""
    detected_topic = cleaned_topic or first_header or (items[0].ref if items else "סוגיה תורנית")
    first_ref = items[0].ref or "סוגיית היסוד"

    # Mermaid Flowchart
    mermaid_nodes = []
    mermaid_nodes.append('flowchart TD')
    mermaid_nodes.append(f'    A["שאלת היסוד: {detected_topic[:40]}"] --> B["מקור 1: {first_ref}"]')
    for i in range(1, min(len(sections), 5)):
        prev_char = chr(ord('B') + i - 1)
        curr_char = chr(ord('B') + i)
        curr_sec = sections[i]
        mermaid_nodes.append(f'    {prev_char} -->|{curr_sec.role_tag}| {curr_char}["מקור {curr_sec.index}: {curr_sec.title[:30]}"]')
    flowchart_code = "\n".join(mermaid_nodes)

    opinion_table = [
        {
            "opinion": sections[0].title if sections else "שיטה ראשונה",
            "reason": "מקור הדין הבסיסי והעמדת המקרה",
            "proof": sections[0].ref or "ש\"ס",
            "nafka_mina": "הגדרת הדין היסודית",
        }
    ]
    if len(sections) > 1:
        opinion_table.append({
            "opinion": sections[1].title,
            "reason": "דיוק או קושיא על הפשט",
            "proof": sections[1].ref or "מפרשים",
            "nafka_mina": "צמצום או הרחבת גדרי הדין",
        })

    chavruta_questions = {
        "peshat": [
            f"מהי נקודת הפתיחה המרכזית העולה מתוך {sections[0].title}?",
            "הסבר את המושג המרכזי המוזכר במקור בלשונך.",
        ],
        "comparison": [
            f"מה ההבדל העיקרי בין דברי {sections[0].title} למקורות הבאים אחריו?",
            "איזו קושיא יישב המקור השני על המקור הראשון?",
        ],
        "sevara": [
            "האם ניתן להציע חילוק מושגי (חקירה) שיסביר את שתי הדרכים בסוגיה?",
            "כיצד משליכה הכרעה זו על מקרים מודרניים דומים?",
        ],
    }

    if user_instruction:
        summary_text = f"ניתוח דף המקורות בהתאם לבקשתך: {user_instruction}\n\nסוגיית {detected_topic} נפרסת לאורך {len(sections)} מקורות מרכזיים, המתווים את המעבר מן הדין היסודי אל הבירור המושגי וההכרעה."
    else:
        summary_text = f"סוגיית {detected_topic} נפרסת לאורך {len(sections)} מקורות מרכזיים, המתווים את המעבר מן הדין היסודי אל הבירור המושגי וההכרעה."

    return CompanionGuide(
        title=f"מהלך הסוגיה — {detected_topic}",
        topic=detected_topic,
        core_inquiry=f"הסוגיה עוסקת בבירור יסודות {detected_topic}, החל ממקורות השורש, דרך שיטות הראשונים והחקירות המרכזיות, ועד לבירור המסקנה וההשלכות המעשיות.",
        flowchart_mermaid=flowchart_code,
        sections=sections,
        opinion_table=opinion_table,
        chavruta_questions=chavruta_questions,
        summary=summary_text,
        citations=citations,
    )
