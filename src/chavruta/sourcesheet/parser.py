"""Source sheet text extraction, segmentation, and rabbinic reference resolution.

Layout-aware ingestion (multi-column PDF, Word paragraphs & tables),
bullet/header segmentation, relative citation resolution ("שם", "עיין שם"),
dibur hamatchil extraction ("ד\"ה"), and author note detection.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from chavruta.corpus.refs import canon_corpus_ref, canonical_ref, daf_amud_to_corpus_n
from chavruta.intents.hebrew_refs import (
    HE_BOOKS,
    HE_TRACTATES,
    _DAF,
    _GEMATRIA,
    _NUM,
    _SEP,
    _book_alt,
    _daf_value,
    _num,
    gematria,
)

_log = logging.getLogger("chavruta.sourcesheet.parser")

# ── Extended Rabbinic Commentators & Code Books ──────────────────────────────

HE_COMMENTATORS: dict[str, str] = {
    'רש"י': "Rashi",
    'רש״י': "Rashi",
    'תוספות': "Tosafot",
    "תוס'": "Tosafot",
    'תוס״': "Tosafot",
    'תוספות ישנים': "Tosafot Yeshanim",
    'תוס\' ישנים': "Tosafot Yeshanim",
    'רמב"ן': "Ramban",
    'רמב״ן': "Ramban",
    'רשב"א': "Rashba",
    'רשב״א': "Rashba",
    'ריטב"א': "Ritva",
    'ריטב״א': "Ritva",
    'ר"ן': "Ran",
    'ר״ן': "Ran",
    'הר"ן': "Ran",
    'הר״ן': "Ran",
    'רא"ש': "Rosh",
    'רא״ש': "Rosh",
    'הרא"ש': "Rosh",
    'הרא״ש': "Rosh",
    'רי"ף': "Rif",
    'רי״ף': "Rif",
    'הרי"ף': "Rif",
    'הרי״ף': "Rif",
    'מאירי': "Meiri",
    'קצות החושן': "Ketzot HaChoshen",
    'קצוה"ח': "Ketzot HaChoshen",
    'נתיבות המשפט': "Netivot HaMishpat",
    'משנה ברורה': "Mishnah Berurah",
    'משנ"ב': "Mishnah Berurah",
    'מגן אברהם': "Magen Avraham",
    'מג"א': "Magen Avraham",
    'טורי זהב': "Taz",
    'ט"ז': "Taz",
    'שפתי כהן': "Shakh",
    'ש"ך': "Shakh",
    'בית יוסף': "Beit Yosef",
    'ב"י': "Beit Yosef",
}

HE_CODES: dict[str, str] = {
    'שולחן ערוך': "Shulchan Arukh",
    'שו"ע': "Shulchan Arukh",
    'שו״ע': "Shulchan Arukh",
    'רמב"ם': "Mishneh Torah",
    'רמבם': "Mishneh Torah",
    'משנה תורה': "Mishneh Torah",
    'טור': "Tur",
    'ארבעה טורים': "Tur",
    'משנה': "Mishnah",
}

# Shulchan Arukh / Tur Sections
HE_HALACHA_SECTIONS: dict[str, str] = {
    'אורח חיים': "Orach Chayim",
    'או"ח': "Orach Chayim",
    'יורה דעה': "Yoreh Deah",
    'יו"ד': "Yoreh Deah",
    'אבן העזר': "Even HaEzer",
    'אה"ע': "Even HaEzer",
    'חושן משפט': "Choshen Mishpat",
    'חו"מ': "Choshen Mishpat",
}


@dataclass
class ParsedSourceItem:
    index: int
    raw_text: str
    header: str
    cleaned_text: str
    ref: str | None = None
    canonical_sefaria_ref: str | None = None
    dibur_hamatchil: str | None = None
    is_author_note: bool = False
    author_note_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Extraction from PDF / Word / Text ────────────────────────────────────────

def extract_sheet_text(raw: bytes | str, filename: str = "", mime: str = "") -> str:
    """Extract usable text from raw uploaded bytes (PDF, Word, or plain text).

    Layout-aware: handles Word paragraphs + tables in flow order, and text line sequences.
    """
    if isinstance(raw, str):
        return raw.strip()

    name = (filename or "").lower()
    m = (mime or "").lower()

    if "word" in m or "officedocument" in m or name.endswith((".docx", ".doc")):
        try:
            import docx

            doc = docx.Document(io.BytesIO(raw))
            lines: list[str] = []
            # Extract paragraphs and table cells in document flow order
            for block in doc.element.body:
                if block.tag.endswith("p"):
                    p = docx.text.paragraph.Paragraph(block, doc)
                    if p.text.strip():
                        lines.append(p.text.strip())
                elif block.tag.endswith("tbl"):
                    tbl = docx.table.Table(block, doc)
                    for row in tbl.rows:
                        row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                        if row_text:
                            lines.append(row_text)
            return "\n\n".join(lines).strip()
        except Exception as exc:
            _log.warning("docx extraction fallback failed: %s", exc)
            return ""

    if "pdf" in m or name.endswith(".pdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(raw))
            pages_text = []
            for page in reader.pages:
                txt = page.extract_text() or ""
                if txt.strip():
                    pages_text.append(txt.strip())
            return "\n\n".join(pages_text).strip()
        except Exception as exc:
            _log.warning("pdf extraction failed: %s", exc)
            return ""

    # Plain text fallback
    try:
        return raw.decode("utf-8", "ignore").strip()
    except Exception:
        return ""


# ── Segmentation & Bullet Split ──────────────────────────────────────────────

_BULLET_RE = re.compile(
    r"(?m)^(?:"
    r"[-*•]\s+|"
    r"\[?\s*(?:אות\s+|מקור\s+|סימן\s+|סעיף\s+)?(?:\d+|[א-ת][״'׳\"]?[א-ת]?)\s*[\].):–-]\s*|"
    r"#{1,4}\s+|"
    r"===+\s*"
    r")",
)

_DH_RE = re.compile(r'(?:ד"ה|ד״ה|דיבור המתחיל)\s+([^\n.,:;–—]+)', re.IGNORECASE)
_AUTHOR_NOTE_RE = re.compile(r"(\((?:ו?צ\"ע|ועיין|הערת|שאלה|לעיון)[^)]+\)|\[(?:ו?צ\"ע|ועיין|הערת|שאלה|לעיון)[^\]]+\])")
_RELATIVE_REF_RE = re.compile(r"\b(?:שם|עיין\s+שם|ע\"ש|ע״ש|שם\s+שם)\b")


def parse_source_sheet(text: str) -> list[ParsedSourceItem]:
    """Segment raw source sheet text into structured ParsedSourceItem objects.

    Maintains contextual reference memory across consecutive items to resolve
    relative references ("שם", "עיין שם", "ד\"ה").
    """
    if not text or not text.strip():
        return []

    clean_text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Strip attachment filename headers (e.g. "### 02 הרב חיים וולפסון - פרישת כהן גדול.docx")
    clean_text = re.sub(r"^\s*###\s+[^\n]+\.(?:docx|pdf|txt|doc)\s*\n?", "", clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r"^\s*###\s+(?:מקור|source)\s*\d*\s*\n?", "", clean_text, flags=re.IGNORECASE)
    clean_text = clean_text.strip()

    # Split text into segments
    splits = [m.start() for m in _BULLET_RE.finditer(clean_text)]
    if not splits:
        splits = [0]

    raw_segments: list[str] = []
    for i in range(len(splits)):
        start = splits[i]
        end = splits[i + 1] if i + 1 < len(splits) else len(clean_text)
        seg = clean_text[start:end].strip()
        if seg:
            raw_segments.append(seg)

    # Fallback if no bullets found: split on double newlines
    if len(raw_segments) <= 1:
        blocks = [b.strip() for b in clean_text.split("\n\n") if b.strip()]
        if len(blocks) > 1:
            raw_segments = blocks

    items: list[ParsedSourceItem] = []
    last_known_ref: str | None = None
    last_known_book: str | None = None

    for idx, raw_seg in enumerate(raw_segments, start=1):
        lines = [line.strip() for line in raw_seg.split("\n") if line.strip()]
        header = lines[0] if lines else ""
        body = "\n".join(lines[1:]) if len(lines) > 1 else lines[0] if lines else ""

        # Extract Dibur Hamatchil if any
        dh_match = _DH_RE.search(raw_seg)
        dh = dh_match.group(1).strip() if dh_match else None

        # Check for author annotations
        note_match = _AUTHOR_NOTE_RE.search(raw_seg)
        author_note = note_match.group(1).strip() if note_match else None
        is_pure_note = bool(author_note and len(author_note) > len(raw_seg) * 0.7)

        # Resolve references
        detected_ref, canonical_sefaria, book_id = _resolve_segment_ref(
            header=header,
            body=body,
            last_known_ref=last_known_ref,
            last_known_book=last_known_book,
            dh=dh,
        )

        if detected_ref:
            last_known_ref = detected_ref
        if book_id:
            last_known_book = book_id

        item = ParsedSourceItem(
            index=idx,
            raw_text=raw_seg,
            header=header,
            cleaned_text=body or raw_seg,
            ref=detected_ref,
            canonical_sefaria_ref=canonical_sefaria,
            dibur_hamatchil=dh,
            is_author_note=is_pure_note,
            author_note_text=author_note,
            metadata={"lines_count": len(lines)},
        )
        items.append(item)

    return items


# ── Reference Resolution Logic ───────────────────────────────────────────────

_STRICT_DAF = r"(?:\d+|[א-ת]{1,2}[\"'״׳][א-ת]|[א-ת][\"'״׳])"
_ANY_DAF = r"(?:\d+|[א-ת]{1,2}[\"'״׳][א-ת]|[א-ת][\"'״׳]|[א-ת]{1,2})"
_EXTENDED_AMUD = r"(?:ע[\"'״׳ ]?[אב]|עמוד\s*[אב]|:\s*|\.\s*|[אב]\b)"

_TALMUD_AMUD_RE = re.compile(
    rf"(?P<tractate>{_book_alt(HE_TRACTATES)})"
    rf"(?:{_SEP}(?:(?:דף|דף\s*סדר)\s*(?P<daf_pre>{_ANY_DAF})|(?P<daf_strict>{_STRICT_DAF})|(?P<daf_amud>[א-ת]{{1,2}})(?={_SEP}?(?:[:.]|ע[\"'״׳ ]?[אב]|עמוד\s*[אב]|$))))?"
    rf"(?:{_SEP}?(?P<amud>{_EXTENDED_AMUD}))?",
)


def _resolve_segment_ref(
    header: str,
    body: str,
    last_known_ref: str | None = None,
    last_known_book: str | None = None,
    dh: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Identify or infer the canonical reference of a segment."""
    search_scope = f"{header} {body[:200]}"

    # Check for relative citation ("שם", "עיין שם")
    is_relative = bool(_RELATIVE_REF_RE.search(header) or _RELATIVE_REF_RE.search(search_scope[:40]))

    # Check for commentator on previous ref or standalone
    for comm_he, comm_en in HE_COMMENTATORS.items():
        comm_pat = rf"(?<![א-ת]){re.escape(comm_he)}(?![א-ת])"
        if re.search(comm_pat, header) or re.search(comm_pat, search_scope[:60]):
            # Check if tractate/book follows the commentator explicitly
            t_match = _TALMUD_AMUD_RE.search(search_scope)
            if t_match:
                tr_name = HE_TRACTATES.get(t_match.group("tractate"))
                daf_raw = t_match.group("daf_pre") or t_match.group("daf_strict") or t_match.group("daf_amud")
                amud_raw = t_match.group("amud") or "a"
                if tr_name and daf_raw:
                    daf_val = _daf_value(daf_raw)
                    if daf_val:
                        amud_letter = "b" if any(b in str(amud_raw) for b in ("ב", "b", ":")) else "a"
                        base_talmud = f"{tr_name}.{daf_val}{amud_letter}"
                        target_ref = f"{comm_en} on {base_talmud}"
                        return target_ref, canonical_ref(target_ref), tr_name
            # If no explicit tractate, inherit from last_known_ref
            if last_known_ref:
                base_ref = last_known_ref
                if " on " in base_ref:
                    base_ref = base_ref.split(" on ", 1)[1]
                target_ref = f"{comm_en} on {base_ref}"
                return target_ref, canonical_ref(target_ref), last_known_book

    # Check for Talmud Bavli
    t_match = _TALMUD_AMUD_RE.search(search_scope)
    if t_match and not is_relative:
        tr_he = t_match.group("tractate")
        tr_name = HE_TRACTATES.get(tr_he)
        daf_raw = t_match.group("daf_pre") or t_match.group("daf_strict") or t_match.group("daf_amud")
        amud_raw = t_match.group("amud") or "a"
        if tr_name and daf_raw:
            daf_val = _daf_value(daf_raw)
            if daf_val:
                amud_letter = "b" if any(b in str(amud_raw) for b in ("ב", "b", ":")) else "a"
                full_ref = f"{tr_name} {daf_val}{amud_letter}"
                return full_ref, canonical_ref(full_ref), tr_name

    # Check for Tanakh
    from chavruta.intents.hebrew_refs import _TANAKH_RE

    tanakh_match = _TANAKH_RE.search(search_scope)
    if tanakh_match and not is_relative:
        book_he = tanakh_match.group("book")
        book_name = HE_BOOKS.get(book_he)
        ch_raw = tanakh_match.group("ch")
        vs_raw = tanakh_match.group("vs")
        if book_name and ch_raw:
            ch_val = _num(ch_raw)
            if ch_val:
                vs_val = _num(vs_raw) if vs_raw else None
                ref_str = f"{book_name}.{ch_val}" + (f".{vs_val}" if vs_val else "")
                return ref_str, canonical_ref(ref_str), book_name

    # Check for Shulchan Arukh / Halacha sections
    for sec_he, sec_en in HE_HALACHA_SECTIONS.items():
        if sec_he in search_scope:
            # Extract Siman
            siman_match = re.search(rf"{re.escape(sec_he)}[^\dא-ת]*(?:סימן|סי'|סעיף)?\s*({_NUM})", search_scope)
            if siman_match:
                siman_val = _num(siman_match.group(1))
                if siman_val:
                    ref_str = f"Shulchan_Arukh,_{sec_en}.{siman_val}"
                    return ref_str, canonical_ref(ref_str), sec_en

    # Relative fallback
    if is_relative and last_known_ref:
        return last_known_ref, canonical_ref(last_known_ref), last_known_book

    return None, None, None
