"""
scripts/process_chunks.py — Chavruta.AI
========================================
ממיר קבצי data/raw/*.json ל-chunks מוכנים ל-ChromaDB.

כל פסוק מניב עד 3 chunks:
  • chumash  — טקסט הפסוק עצמו (עברית + אנגלית)
  • rashi    — פירוש רש"י (אם קיים)
  • ramban   — פירוש רמב"ן (אם קיים)

טכני:
  • MAX_TOKENS = 512  (הערכה: 4 תווים לטוקן → 2048 תווים)
  • OVERLAP    = 50 טוקן  → 200 תווים
  • חלוקה חכמה: ניסיון לחתוך על גבול משפט (". ") לפני הגבול
  • מטא-נתונים שטוחים — תואם לדרישות ChromaDB (str/int/float/bool בלבד)
  • document  = טקסט דו-לשוני: "עברית מנורמלת\\nאנגלית" (טוב לembedding רב-לשוני)

פלט:
  data/processed/all_chunks.json
    {
      "metadata": { "total_chunks": N, "by_type": {...}, "by_book": {...}, ... },
      "chunks": [ { "id": ..., "document": ..., "metadata": {...} }, ... ]
    }

הרצה:
  python scripts/process_chunks.py
  python scripts/process_chunks.py --input data/raw/bereishit.json
  python scripts/process_chunks.py --input data/raw/bereishit.json data/raw/shemot.json
  python scripts/process_chunks.py --stats   # רק מדפיס סטטיסטיקות ללא שמירה
"""

import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Iterator

# ─── נתיבים ──────────────────────────────────────────────────────────────────
ROOT_DIR       = Path(__file__).resolve().parent.parent
DATA_RAW       = ROOT_DIR / "data" / "raw"
DATA_PROCESSED = ROOT_DIR / "data" / "processed"
DEFAULT_OUTPUT = DATA_PROCESSED / "all_chunks.json"

# ─── פרמטרי chunking ─────────────────────────────────────────────────────────
CHARS_PER_TOKEN = 4          # הערכה: תו אחד ≈ 0.25 טוקן (לאנגלית; עברית בד"כ יותר)
MAX_TOKENS      = 512
OVERLAP_TOKENS  = 50
MAX_CHARS       = MAX_TOKENS  * CHARS_PER_TOKEN   # 2048
OVERLAP_CHARS   = OVERLAP_TOKENS * CHARS_PER_TOKEN  # 200

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════════
# פונקציות עזר: חלוקת טקסט
# ════════════════════════════════════════════════════════════════════════════════

def split_text(text: str, max_chars: int = MAX_CHARS,
               overlap_chars: int = OVERLAP_CHARS) -> list[str]:
    """
    מחלק טקסט ארוך ל-chunks עם overlap.

    אסטרטגיה:
      1. אם הטקסט קצר מ-max_chars — מחזיר רשימה עם פריט אחד.
      2. אחרת — מחפש גבול משפט (". " / "! " / "? ") בטווח [max_chars*0.7, max_chars].
         אם לא מצא — חותך בפסיק + רווח, ואם גם לא — חותך בגבול המילה הקרוב.
      3. ה-overlap: ה-chunk הבא מתחיל OVERLAP_CHARS לפני הנקודה שבה הסתיים הקודם.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + max_chars
        if end >= len(text):
            chunk = text[start:].strip()
            if chunk:
                chunks.append(chunk)
            break

        # חיפוש גבול משפט (". " / "! " / "? ") בטווח האחרון 30% מה-chunk
        window_start = start + int(max_chars * 0.7)
        best_cut = -1

        for sep in (". ", "! ", "? "):
            pos = text.rfind(sep, window_start, end)
            if pos != -1:
                best_cut = max(best_cut, pos + len(sep))  # אחרי הסיום

        # fallback: פסיק
        if best_cut == -1:
            pos = text.rfind(", ", window_start, end)
            if pos != -1:
                best_cut = pos + 2

        # fallback: גבול מילה
        if best_cut == -1:
            pos = text.rfind(" ", window_start, end)
            best_cut = pos + 1 if pos != -1 else end

        chunk = text[start:best_cut].strip()
        if chunk:
            chunks.append(chunk)

        # ה-chunk הבא מתחיל עם overlap
        start = max(start + 1, best_cut - overlap_chars)

    return chunks if chunks else [text[:max_chars]]


def approx_tokens(text: str) -> int:
    """הערכת מספר טוקנים: len(text) / CHARS_PER_TOKEN."""
    return max(1, len(text) // CHARS_PER_TOKEN)


# ════════════════════════════════════════════════════════════════════════════════
# בניית document text — טקסט דו-לשוני לembedding
# ════════════════════════════════════════════════════════════════════════════════

def build_chumash_doc(verse: dict) -> str:
    """
    טקסט ה-document לchunk מסוג chumash.
    פורמט: "[Chumash] ספר פרק:פסוק\\nעברית\\nאנגלית"
    """
    prefix = f"[Chumash] {verse['book']} {verse['chapter']}:{verse['verse']}"
    he = verse.get("text_he_normalized") or verse.get("text_he", "")
    en = verse.get("text_en", "")
    parts = [prefix]
    if he:
        parts.append(he)
    if en:
        parts.append(en)
    return "\n".join(parts)


def build_commentary_doc(verse: dict, ctype: str) -> str:
    """
    טקסט ה-document לchunk של פירוש (rashi/ramban).
    פורמט: "[Rashi] ספר פרק:פסוק\\nעברית\\nאנגלית"
    """
    label = "Rashi" if ctype == "rashi" else "Ramban"
    prefix = f"[{label}] {verse['book']} {verse['chapter']}:{verse['verse']}"
    comm = verse.get(ctype, {})
    he = comm.get("text_he_normalized") or comm.get("text_he", "")
    en = comm.get("text_en", "")
    parts = [prefix]
    if he:
        parts.append(he)
    if en:
        parts.append(en)
    return "\n".join(parts)


# ════════════════════════════════════════════════════════════════════════════════
# בניית מטא-נתונים שטוחים (תואם ChromaDB)
# ════════════════════════════════════════════════════════════════════════════════

def base_metadata(verse: dict) -> dict:
    """שדות ביסוס משותפים לכל chunk של פסוק זה."""
    return {
        "verse_id":    verse["verse_id"],
        "book":        verse["book"],
        "book_he":     verse.get("book_he", ""),
        "book_en":     verse.get("book_en", ""),
        "book_num":    int(verse.get("book_num", 0)),
        "chapter":     int(verse["chapter"]),
        "verse":       int(verse["verse"]),
        "has_rashi":   bool(verse.get("rashi", {}).get("has_content", False)),
        "has_ramban":  bool(verse.get("ramban", {}).get("has_content", False)),
        # שמור את הטקסטים המקוריים במטא-נתונים לשימוש בתצוגה
        "text_en":     verse.get("text_en", ""),
        "text_he":     verse.get("text_he", ""),
    }


def chumash_metadata(verse: dict, chunk_idx: int, total: int,
                     char_count: int) -> dict:
    meta = base_metadata(verse)
    meta.update({
        "chunk_type":           "chumash",
        "chunk_index":          chunk_idx,
        "total_chunks_for_type": total,
        "source_url": (
            f"https://www.sefaria.org/{verse['book']}.{verse['chapter']}.{verse['verse']}"
        ),
        "char_count":    char_count,
        "approx_tokens": approx_tokens("x" * char_count),
    })
    return meta


def commentary_metadata(verse: dict, ctype: str, chunk_idx: int,
                         total: int, char_count: int) -> dict:
    meta = base_metadata(verse)
    comm = verse.get(ctype, {})
    label = "Rashi" if ctype == "rashi" else "Ramban"
    meta.update({
        "chunk_type":            ctype,
        "chunk_index":           chunk_idx,
        "total_chunks_for_type": total,
        "source_url":            comm.get("source_url", ""),
        "commentator":           label,
        "commentary_text_en":    comm.get("text_en", ""),
        "commentary_text_he":    comm.get("text_he", ""),
        "char_count":            char_count,
        "approx_tokens":         approx_tokens("x" * char_count),
    })
    return meta


# ════════════════════════════════════════════════════════════════════════════════
# יצירת chunks לפסוק בודד
# ════════════════════════════════════════════════════════════════════════════════

def verse_to_chunks(verse: dict) -> Iterator[dict]:
    """
    Generator: מניב עד 3 * N chunks לפסוק (N = מספר חלקים אם הטקסט ארוך).

    chunk format (תואם ChromaDB):
      {
        "id":       str,          ← chunk_id ייחודי
        "document": str,          ← טקסט לembedding
        "metadata": { ... }       ← ערכים שטוחים בלבד
      }
    """
    vid = verse["verse_id"]

    # ── 1. Chumash ──────────────────────────────────────────────────────────
    chumash_text = build_chumash_doc(verse)
    chumash_parts = split_text(chumash_text)
    for idx, part in enumerate(chumash_parts):
        chunk_id = f"{vid}_chumash_{idx}"
        yield {
            "id":       chunk_id,
            "document": part,
            "metadata": chumash_metadata(verse, idx, len(chumash_parts), len(part)),
        }

    # ── 2. Rashi ─────────────────────────────────────────────────────────────
    rashi = verse.get("rashi", {})
    if rashi.get("has_content"):
        rashi_text  = build_commentary_doc(verse, "rashi")
        rashi_parts = split_text(rashi_text)
        for idx, part in enumerate(rashi_parts):
            chunk_id = f"{vid}_rashi_{idx}"
            yield {
                "id":       chunk_id,
                "document": part,
                "metadata": commentary_metadata(verse, "rashi", idx,
                                                len(rashi_parts), len(part)),
            }

    # ── 3. Ramban ────────────────────────────────────────────────────────────
    ramban = verse.get("ramban", {})
    if ramban.get("has_content"):
        ramban_text  = build_commentary_doc(verse, "ramban")
        ramban_parts = split_text(ramban_text)
        for idx, part in enumerate(ramban_parts):
            chunk_id = f"{vid}_ramban_{idx}"
            yield {
                "id":       chunk_id,
                "document": part,
                "metadata": commentary_metadata(verse, "ramban", idx,
                                                len(ramban_parts), len(part)),
            }


# ════════════════════════════════════════════════════════════════════════════════
# עיבוד קובץ ספר שלם
# ════════════════════════════════════════════════════════════════════════════════

def process_book_file(path: Path) -> tuple[list[dict], dict]:
    """
    קורא קובץ JSON של ספר ומחזיר (chunks_list, stats_dict).
    """
    log.info("Processing: %s", path.name)
    with open(path, encoding="utf-8") as f:
        book_data = json.load(f)

    book_name = book_data.get("book", path.stem)
    verses    = book_data.get("verses", [])

    chunks: list[dict] = []
    counts  = {"chumash": 0, "rashi": 0, "ramban": 0}
    split_c = {"chumash": 0, "rashi": 0, "ramban": 0}  # פסוקים שפוצלו

    for verse in verses:
        per_type: dict[str, int] = {"chumash": 0, "rashi": 0, "ramban": 0}
        for chunk in verse_to_chunks(verse):
            ctype = chunk["metadata"]["chunk_type"]
            counts[ctype] += 1
            per_type[ctype] += 1
            chunks.append(chunk)
        # ספירת פיצולים
        for ctype, cnt in per_type.items():
            if cnt > 1:
                split_c[ctype] += 1

    stats = {
        "book":         book_name,
        "total_verses": len(verses),
        "total_chunks": len(chunks),
        "by_type":      dict(counts),
        "split_verses": dict(split_c),   # פסוקים שנוצרו מהם >1 chunk
    }
    log.info(
        "  %s: %d פסוקים → %d chunks  "
        "(chumash:%d | rashi:%d | ramban:%d)",
        book_name, len(verses), len(chunks),
        counts["chumash"], counts["rashi"], counts["ramban"],
    )
    return chunks, stats


# ════════════════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="ממיר קבצי RAW Torah → chunks ל-ChromaDB"
    )
    p.add_argument(
        "--input", "-i", nargs="+", type=Path,
        help="קבצי JSON קלט (ברירת מחדל: כל *.json ב-data/raw/ חוץ מ-cache)",
    )
    p.add_argument(
        "--output", "-o", type=Path, default=DEFAULT_OUTPUT,
        help=f"קובץ פלט JSON (ברירת מחדל: {DEFAULT_OUTPUT})",
    )
    p.add_argument(
        "--stats", action="store_true",
        help="מדפיס סטטיסטיקות בלבד, לא שומר פלט",
    )
    p.add_argument(
        "--max-tokens", type=int, default=MAX_TOKENS,
        help=f"גודל chunk מקסימלי בטוקנים (ברירת מחדל: {MAX_TOKENS})",
    )
    p.add_argument(
        "--overlap-tokens", type=int, default=OVERLAP_TOKENS,
        help=f"overlap בטוקנים (ברירת מחדל: {OVERLAP_TOKENS})",
    )
    return p.parse_args()


def find_input_files(custom: list[Path] | None) -> list[Path]:
    """מוצא קבצי JSON קלט: מה-CLI, או כל *.json ב-data/raw/ (חוץ מ-cache)."""
    if custom:
        missing = [p for p in custom if not p.exists()]
        if missing:
            log.error("לא נמצאו קבצים: %s", ", ".join(str(p) for p in missing))
            sys.exit(1)
        return custom

    files = sorted(
        p for p in DATA_RAW.glob("*.json")
        if p.is_file() and "cache" not in p.parts
    )
    if not files:
        log.error("לא נמצאו קבצי JSON ב-%s", DATA_RAW)
        sys.exit(1)
    return files


def print_report(all_stats: list[dict], total_chunks: int) -> None:
    """מדפיס דוח סופי."""
    print("\n" + "═" * 62)
    print("  📦  Chavruta.AI — Chunk Processing Report")
    print("═" * 62)
    print(f"  {'ספר':<12} {'פסוקים':>8}  {'סה\"כ chunks':>12}  "
          f"{'chumash':>8}  {'rashi':>7}  {'ramban':>7}")
    print("─" * 62)

    total_v = total_ch = total_r = total_rb = 0
    for s in all_stats:
        v   = s["total_verses"]
        ch  = s["by_type"]["chumash"]
        r   = s["by_type"]["rashi"]
        rb  = s["by_type"]["ramban"]
        tot = s["total_chunks"]
        print(f"  {s['book']:<12} {v:>8}  {tot:>12}  {ch:>8}  {r:>7}  {rb:>7}")
        total_v  += v
        total_ch += ch
        total_r  += r
        total_rb += rb

    print("─" * 62)
    print(f"  {'סה\"כ':<12} {total_v:>8}  {total_chunks:>12}  "
          f"{total_ch:>8}  {total_r:>7}  {total_rb:>7}")
    print("═" * 62)
    print(f"\n  ✅  סה\"כ chunks: {total_chunks:,}")
    rashi_pct  = 100 * total_r  / total_v if total_v else 0
    ramban_pct = 100 * total_rb / total_v if total_v else 0
    print(f"      רש\"י כיסוי:   {rashi_pct:.1f}% מהפסוקים")
    print(f"      רמב\"ן כיסוי: {ramban_pct:.1f}% מהפסוקים")
    print()


def main() -> None:
    args = parse_args()

    # עדכן קבועים אם הועברו דגלים
    global MAX_CHARS, OVERLAP_CHARS
    MAX_CHARS     = args.max_tokens    * CHARS_PER_TOKEN
    OVERLAP_CHARS = args.overlap_tokens * CHARS_PER_TOKEN

    input_files = find_input_files(args.input)
    log.info("קבצי קלט: %s", [p.name for p in input_files])
    log.info("פרמטרים: max_tokens=%d (%d תווים) | overlap=%d (%d תווים)",
             args.max_tokens, MAX_CHARS, args.overlap_tokens, OVERLAP_CHARS)

    all_chunks: list[dict] = []
    all_stats:  list[dict] = []

    for path in input_files:
        chunks, stats = process_book_file(path)
        all_chunks.extend(chunks)
        all_stats.append(stats)

    # ── בדיקת ייחודיות chunk IDs ────────────────────────────────────────────
    ids = [c["id"] for c in all_chunks]
    dupes = len(ids) - len(set(ids))
    if dupes:
        log.warning("⚠️  נמצאו %d chunk IDs כפולים!", dupes)
    else:
        log.info("✔ כל %d chunk IDs ייחודיים", len(ids))

    # ── הדפסת דוח ───────────────────────────────────────────────────────────
    print_report(all_stats, len(all_chunks))

    if args.stats:
        log.info("--stats: לא שומר קובץ.")
        return

    # ── שמירת פלט ───────────────────────────────────────────────────────────
    output_path: Path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # סיכום גלובלי
    by_type_global: dict[str, int] = {"chumash": 0, "rashi": 0, "ramban": 0}
    by_book_global: dict[str, int] = {}
    for s in all_stats:
        for t, n in s["by_type"].items():
            by_type_global[t] += n
        by_book_global[s["book"]] = s["total_chunks"]

    output = {
        "metadata": {
            "generated_at":   datetime.now(timezone.utc).isoformat(),
            "source_files":   [p.name for p in input_files],
            "total_chunks":   len(all_chunks),
            "total_verses":   sum(s["total_verses"] for s in all_stats),
            "by_type":        by_type_global,
            "by_book":        by_book_global,
            "chunking": {
                "max_tokens":     args.max_tokens,
                "overlap_tokens": args.overlap_tokens,
                "chars_per_token": CHARS_PER_TOKEN,
                "max_chars":      MAX_CHARS,
                "overlap_chars":  OVERLAP_CHARS,
            },
            "book_stats": all_stats,
        },
        "chunks": all_chunks,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    log.info("✅  נשמר: %s  (%.1f MB | %d chunks)",
             output_path, size_mb, len(all_chunks))
    print(f"  📄  פלט: {output_path}")
    print(f"      גודל: {size_mb:.1f} MB\n")


if __name__ == "__main__":
    main()
