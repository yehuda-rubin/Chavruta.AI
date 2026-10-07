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


# Commentators that exist only on the Talmud. Handing one of these a Tanakh base ("Tosafot on
# Leviticus.8") is never right, so such a ref is not inherited from a neighbouring pasuk.
_TALMUD_ONLY_COMMENTATORS = frozenset({
    "Tosafot", "Tosafot Yeshanim", "Rashba", "Ritva", "Ran", "Rosh", "Rif", "Meiri",
})
_TALMUD_REF_RE = re.compile(r"\s\d+[ab]$")

# Lines that are about the shiur, not the sources: a start time, "בס״ד", a venue. They sit between the
# outline and the first source and otherwise get glued onto the last outline entry.
_LOGISTICS_LINE_RE = re.compile(
    r"^(?:בס\"ד|בס״ד|בעזרת\s+ה['׳]?)\b|\b\d{1,2}[:.]\d{2}\b|^שיעור\s+[א-ת]\b",
)
_FILENAME_HEADER_RE = re.compile(r"^\s*###\s+[^\n]+\.(?:docx|pdf|txt|doc)\s*\n?", re.IGNORECASE)
_HE_TRACTATE_MENTION_RE = re.compile(rf"מסכת\s+(?P<tractate>{_book_alt(HE_TRACTATES)})")
_GEMARA_CUE_RE = re.compile(r"גמרא|סוגיית|סוגיה")
# A daf given the way a teacher writes a "station": "ב, א" / "ג', ב'" (daf letter, comma, amud letter).
_STATION_RE = re.compile(r"(?<![א-ת])([א-ת])['׳]?\s*,\s*([אב])['׳]?(?![א-ת])")
_VERSE_RANGE_RE = re.compile(
    rf"פסוקים?\s+(?P<v1>{_NUM}|[א-ת]{{1,3}})\s*(?:[-–—]|עד)\s*(?P<v2>{_NUM}|[א-ת]{{1,3}})"
)
_MAX_RANGE_AMUDIM = 8


def extract_sheet_title(text: str) -> str:
    """The sheet's own title — its first prose line after any attachment-filename header.

    A user's instruction ("summarize the flow") says what to do, not what the sheet is about; the
    topic hint was falling back on it. The title line ("פרישת כהן גדול ביום הכפורים – שיעור ראשון")
    is the better label. Empty when the first line is a bullet or a bare reference.
    """
    body = _FILENAME_HEADER_RE.sub("", (text or "").replace("\r\n", "\n"), count=1).strip()
    for line in body.split("\n"):
        line = line.strip()
        if not line:
            continue
        if _BULLET_RE.match(line) or len(line) > 90:
            return ""
        return line
    return ""


def _default_tractate(text: str) -> str | None:
    """A tractate the sheet announces once ("לומדים מסכת יומא") so a later "סוגיית הגמרא" can use it."""
    m = _HE_TRACTATE_MENTION_RE.search(text or "")
    return HE_TRACTATES.get(m.group("tractate")) if m else None


def _amud_linear(daf: int, amud: str) -> int:
    return daf * 2 + (1 if amud == "b" else 0)


def _gemara_stations(segment: str, tractate: str) -> list[str]:
    """Every amud from the first to the last "station" the segment names, e.g. ב,א … ג,ב → 2a,2b,3a,3b.

    Returns [] when fewer than one valid station is found or the span is implausibly wide.
    """
    points: list[int] = []
    for m in _STATION_RE.finditer(segment):
        daf = _daf_value(m.group(1))
        if daf and 2 <= daf <= 180:
            points.append(_amud_linear(daf, "a" if m.group(2) == "א" else "b"))
    if not points:
        return []
    lo, hi = min(points), max(points)
    if hi - lo + 1 > _MAX_RANGE_AMUDIM:
        return []
    return [f"{tractate} {n // 2}{'b' if n % 2 else 'a'}" for n in range(lo, hi + 1)]


def _verse_range(header: str, book: str, chapter: int) -> list[str]:
    """"ויקרא ח' פסוקים לג – לו" → [Leviticus.8.33 … Leviticus.8.36]; [] if no verse range is named."""
    m = _VERSE_RANGE_RE.search(header)
    if not m:
        return []
    v1, v2 = _daf_value(m.group("v1")), _daf_value(m.group("v2"))
    if not v1 or not v2 or v2 < v1 or v2 - v1 > 40:
        return []
    return [f"{book}.{chapter}.{v}" for v in range(v1, v2 + 1)]


def _quoted_text(raw_seg: str) -> str:
    """The sheet's own quotations: lines that open with a quotation mark and run long enough to be a source.

    A segment with such text carries the source itself, so the analysis must use THAT text and not
    whatever the corpus holds for the item's base reference (a Rishonim excerpt filed under "Yoma 3b"
    is not the gemara on Yoma 3b).
    """
    quoted = [
        line.strip() for line in raw_seg.split("\n")
        if line.strip().startswith(('"', "“", "״")) and len(line.strip()) >= 40
    ]
    return "\n".join(quoted)


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
    r"\[?\s*(?:אות\s+|מקור\s+|סימן\s+|סעיף\s+)?(?P<bullet>\d+|[א-ת][״'׳\"]?[א-ת]?)\s*[\].)–-]\s*|"
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
    default_tractate = _default_tractate(clean_text)
    clean_text = "\n".join(
        line for line in clean_text.split("\n")
        if not (len(line.strip()) < 60 and _LOGISTICS_LINE_RE.search(line.strip()))
    )

    # Split text into segments
    matches = list(_BULLET_RE.finditer(clean_text))
    if not matches:
        raw_segments = [clean_text]
    else:
        raw_tuples: list[tuple[str, str]] = []
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(clean_text)
            seg = clean_text[start:end].strip()
            bullet_key = m.group("bullet") or str(i + 1)
            bullet_key = re.sub(r"[\"'\s״׳]", "", bullet_key)
            if seg:
                raw_tuples.append((bullet_key, seg))

        # If bullet keys repeat (e.g. syllabus/outline followed by full source text), merge them
        seen_keys = set()
        has_repeats = False
        for k, _ in raw_tuples:
            if k in seen_keys and len(k) <= 2:
                has_repeats = True
                break
            seen_keys.add(k)

        if has_repeats:
            merged_by_key: dict[str, str] = {}
            for k, seg in raw_tuples:
                if k not in merged_by_key:
                    merged_by_key[k] = seg
                else:
                    # The outline entry stays first: its line is the item's title. Putting the
                    # longer half first made a source's quoted body its header.
                    merged_by_key[k] = f"{merged_by_key[k]}\n\n{seg}"
            raw_segments = list(merged_by_key.values())
        else:
            raw_segments = [s for _, s in raw_tuples]

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
        if not lines:
            continue

        # If the first line is just an isolated bullet marker (e.g. "א." or "1."), look for the real title
        first_line_idx = 0
        if re.match(r"^\[?\s*(?:אות\s+|מקור\s+)?(?:\d+|[א-ת])\s*[\].)–-]?\s*$", lines[0]):
            first_line_idx = 1 if len(lines) > 1 else 0

        header = lines[first_line_idx] if lines else ""
        body = "\n".join(lines[first_line_idx + 1:]) if len(lines) > first_line_idx + 1 else lines[0] if lines else ""

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

        if not detected_ref:
            # A header that opens with a book and a bare Hebrew-letter chapter ("במדבר יט"). The strict
            # prose matcher rejects an unmarked numeral; right after a bullet it is unambiguous.
            lead = _BULLET_RE.sub("", header, count=1).strip()
            hb = re.match(rf"(?P<book>{_book_alt(HE_BOOKS)})\s+(?P<ch>[א-ת]{{1,3}})(?![א-ת])", lead)
            ch = _daf_value(hb.group("ch")) if hb else None
            if hb and ch and ch <= 150:
                detected_ref = f"{HE_BOOKS[hb.group('book')]}.{ch}"
                canonical_sefaria = canonical_ref(detected_ref)
                book_id = HE_BOOKS[hb.group("book")]

        ref_range: list[str] = []
        if detected_ref and re.fullmatch(r"[A-Za-z_]+\.\d+", detected_ref):
            # "ויקרא ח' פסוקים לג – לו" must anchor on those verses, not on the whole chapter.
            book, chapter = detected_ref.rsplit(".", 1)
            ref_range = _verse_range(header, book, int(chapter))
            if ref_range:
                detected_ref = ref_range[0]
                canonical_sefaria = canonical_ref(detected_ref)
        elif not detected_ref and default_tractate and _GEMARA_CUE_RE.search(header):
            ref_range = _gemara_stations(raw_seg, default_tractate)
            if ref_range:
                detected_ref = ref_range[0]
                canonical_sefaria = canonical_ref(detected_ref)
                book_id = default_tractate

        # Context for "שם" / a bare "רש״י" carries over only from the item right before this one, and
        # only when that item named ONE place. Carried further it attached a Tosafot to a pasuk.
        last_known_ref = None if ref_range and len(ref_range) > 1 and " " in (detected_ref or "") else detected_ref
        last_known_book = book_id if last_known_ref else None

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
            metadata={
                "lines_count": len(lines),
                **({"ref_range": ref_range} if len(ref_range) > 1 else {}),
                **({"quoted_text": _quoted_text(raw_seg)} if _quoted_text(raw_seg) else {}),
            },
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
            # Check if tractate follows the commentator explicitly
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

            # Check if Tanakh follows the commentator explicitly
            from chavruta.intents.hebrew_refs import _TANAKH_RE

            tanakh_m = _TANAKH_RE.search(search_scope)
            if tanakh_m:
                b_he = tanakh_m.group("book")
                b_name = HE_BOOKS.get(b_he)
                c_raw = tanakh_m.group("ch")
                v_raw = tanakh_m.group("vs")
                if b_name and c_raw:
                    c_val = _num(c_raw)
                    if c_val:
                        v_val = _num(v_raw) if v_raw else None
                        base_tanakh = f"{b_name}.{c_val}" + (f".{v_val}" if v_val else "")
                        target_ref = f"{comm_en} on {base_tanakh}"
                        return target_ref, canonical_ref(target_ref), b_name

            # If no explicit book/tractate, inherit from last_known_ref
            if last_known_ref:
                base_ref = last_known_ref
                if " on " in base_ref:
                    base_ref = base_ref.split(" on ", 1)[1]
                if comm_en in _TALMUD_ONLY_COMMENTATORS and not _TALMUD_REF_RE.search(base_ref):
                    continue
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
