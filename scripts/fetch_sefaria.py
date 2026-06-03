"""
scripts/fetch_sefaria.py — Chavruta.AI
======================================
מוריד מ-Sefaria API את חמישה חומשי תורה עם פירושי רש"י ורמב"ן,
פסוק לפסוק, ושומר כ-JSON מקומי ב-data/raw/.

תכונות:
  • Rate limiting — 0.4 ש' בין קריאות (≈2.5 req/sec), backoff אוטומטי
  • Caching — כל פרק נשמר בקובץ ביניים; הסקריפט ממשיך ממקום שנעצר
  • tqdm progress bars — ספר → פרק → שלב (פסוק/רש"י/רמב"ן)
  • Retry עם exponential backoff על שגיאות רשת / 429 / 5xx
  • דוח סופי על פירושים חסרים (פסוקים שאין להם רש"י / רמב"ן)

פלט:
  data/raw/
  ├── cache/                     ← ביניים (פרקים גולמיים, ניתן למחוק לאחר מכן)
  │   ├── Bereishit_ch01_text.json
  │   ├── Bereishit_ch01_rashi.json
  │   └── ...
  ├── bereishit.json             ← ספר מלא, פסוק לפסוק
  ├── shemot.json
  └── ...

פקד הרצה:
  python scripts/fetch_sefaria.py
  python scripts/fetch_sefaria.py --books Bereishit Shemot   # ספרים נבחרים
  python scripts/fetch_sefaria.py --clear-cache              # מחיקת cache והורדה מחדש
  python scripts/fetch_sefaria.py --dry-run                  # רק מדפיס תוכנית, לא מוריד
"""

import sys
import json
import time
import argparse
import logging
import re
import unicodedata
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm import tqdm

# ─── נתיבים ──────────────────────────────────────────────────────────────────
ROOT_DIR  = Path(__file__).resolve().parent.parent
DATA_RAW  = ROOT_DIR / "data" / "raw"
CACHE_DIR = DATA_RAW / "cache"

# ─── הגדרות API ──────────────────────────────────────────────────────────────
SEFARIA_BASE = "https://www.sefaria.org/api"
REQUEST_DELAY   = 0.4     # שניות בין קריאות רגילות
BACKOFF_BASE    = 2.0     # בסיס ל-exponential backoff
MAX_RETRIES     = 5       # נסיונות מקסימליים לבקשה כושלת
TIMEOUT         = 30      # timeout לבקשת HTTP

# ─── ספרים ───────────────────────────────────────────────────────────────────
BOOKS = [
    {"en": "Genesis",     "sefaria": "Bereishit", "he": "בראשית", "num": 1},
    {"en": "Exodus",      "sefaria": "Shemot",    "he": "שמות",   "num": 2},
    {"en": "Leviticus",   "sefaria": "Vayikra",   "he": "ויקרא",  "num": 3},
    {"en": "Numbers",     "sefaria": "Bamidbar",  "he": "במדבר",  "num": 4},
    {"en": "Deuteronomy", "sefaria": "Devarim",   "he": "דברים",  "num": 5},
]

# שמות הפירושים כפי שמופיעים ב-Sefaria (תו space לפני שם הספר)
COMMENTATORS = {
    "rashi":  "Rashi on",
    "ramban": "Ramban on",
}

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(ROOT_DIR / "fetch_sefaria.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════════
# עזר: ניקוי טקסט
# ════════════════════════════════════════════════════════════════════════════════

def clean_html(text: str) -> str:
    """מסיר תגיות HTML ו-entities מטקסט Sefaria."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = (text
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&#39;", "'")
            .replace("&nbsp;", " "))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_hebrew(text: str) -> str:
    """מנרמל טקסט עברי: מסיר ניקוד וטעמים, שומר על אותיות ורווחים."""
    if not text:
        return ""
    # טווח ניקוד עברי U+0591–U+05C7 (טעמים + ניקוד)
    text = re.sub(r"[֑-ׇ]", "", text)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def join_commentary_verse(raw: Any) -> str:
    """
    פירוש Sefaria לפסוק יכול להיות:
      - str       → הפירוש עצמו
      - list[str] → מספר דיבורים; מחברים ברווח
      - list[list[str]] → שכבות נוספות
    מחזיר str מאוחד ונקי.
    """
    if raw is None:
        return ""
    if isinstance(raw, str):
        return clean_html(raw)
    if isinstance(raw, list):
        parts = []
        for item in raw:
            if isinstance(item, str):
                parts.append(clean_html(item))
            elif isinstance(item, list):
                parts.append(" ".join(clean_html(s) for s in item if isinstance(s, str)))
        return " ".join(p for p in parts if p)
    return ""


# ════════════════════════════════════════════════════════════════════════════════
# SefariaClient — HTTP + caching + rate-limit
# ════════════════════════════════════════════════════════════════════════════════

class SefariaClient:
    """
    לקוח HTTP ל-Sefaria API עם:
      • Session + HTTPAdapter עם Retry מובנה (שגיאות רשת)
      • Rate limiting בין קריאות
      • File-based cache: כל תגובה נשמרת ל-JSON בנפרד
      • Exponential backoff ל-429 / 5xx
    """

    def __init__(self, cache_dir: Path, delay: float = REQUEST_DELAY,
                 max_retries: int = MAX_RETRIES):
        self.cache_dir = cache_dir
        self.delay     = delay
        self.max_retries = max_retries
        self._last_request = 0.0

        # HTTPAdapter עם retry על שגיאות חיבור (לא על 4xx/5xx — אנחנו מטפלים בהם ידנית)
        session = requests.Session()
        adapter = HTTPAdapter(max_retries=Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"],
        ))
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({
            "User-Agent": "Chavruta.AI/1.0 (educational Torah RAG; rubinri@gmail.com)"
        })
        self.session = session

    # ── cache helpers ──────────────────────────────────────────────────────────

    def _cache_path(self, cache_key: str) -> Path:
        safe = re.sub(r"[^\w\-.]", "_", cache_key)
        return self.cache_dir / f"{safe}.json"

    def _load_cache(self, cache_key: str) -> Optional[dict]:
        p = self._cache_path(cache_key)
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                log.warning("Cache corrupted for %s — re-fetching", cache_key)
        return None

    def _save_cache(self, cache_key: str, data: dict) -> None:
        p = self._cache_path(cache_key)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def clear_cache(self) -> None:
        """מוחק את כל קבצי ה-cache."""
        count = 0
        for f in self.cache_dir.glob("*.json"):
            f.unlink()
            count += 1
        log.info("Cache cleared: %d files deleted", count)

    # ── HTTP ───────────────────────────────────────────────────────────────────

    def _wait(self) -> None:
        """Rate limiting: ממתין לפחות self.delay שניות מהבקשה הקודמת."""
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    def get(self, url: str, cache_key: str, params: Optional[dict] = None) -> Optional[dict]:
        """
        שולח GET ל-url עם caching ו-backoff.
        מחזיר dict של התגובה, או None אם כשל לאחר כל הנסיונות.
        """
        # בדיקת cache תחילה
        cached = self._load_cache(cache_key)
        if cached is not None:
            return cached

        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            self._wait()
            try:
                self._last_request = time.monotonic()
                resp = self.session.get(url, params=params, timeout=TIMEOUT)

                if resp.status_code == 200:
                    data = resp.json()
                    self._save_cache(cache_key, data)
                    return data

                if resp.status_code == 404:
                    # פירוש לא קיים לפסוק זה — תגובה תקינה, שומר {} כ-cache
                    log.debug("404 for %s — no commentary", url)
                    self._save_cache(cache_key, {})
                    return {}

                if resp.status_code == 429:
                    wait = BACKOFF_BASE ** attempt
                    log.warning("Rate limited (429). Waiting %.1fs before retry %d/%d",
                                wait, attempt, self.max_retries)
                    time.sleep(wait)
                    continue

                if resp.status_code >= 500:
                    wait = BACKOFF_BASE ** attempt
                    log.warning("Server error %d for %s. Retry %d/%d in %.1fs",
                                resp.status_code, url, attempt, self.max_retries, wait)
                    time.sleep(wait)
                    continue

                log.error("Unexpected HTTP %d for %s", resp.status_code, url)
                return None

            except requests.exceptions.Timeout:
                log.warning("Timeout on %s (attempt %d/%d)", url, attempt, self.max_retries)
                time.sleep(BACKOFF_BASE ** attempt)
                last_exc = Exception("Timeout")
            except requests.exceptions.ConnectionError as e:
                log.warning("Connection error: %s (attempt %d/%d)", e, attempt, self.max_retries)
                time.sleep(BACKOFF_BASE ** attempt)
                last_exc = e
            except (requests.exceptions.JSONDecodeError, ValueError) as e:
                log.error("JSON decode error for %s: %s", url, e)
                return None

        log.error("All %d retries exhausted for %s. Last error: %s",
                  self.max_retries, url, last_exc)
        return None

    # ── Sefaria-specific ───────────────────────────────────────────────────────

    def fetch_index(self, sefaria_name: str) -> Optional[dict]:
        """מביא את אינדקס הספר (מספרי פרקים ופסוקים)."""
        url = f"{SEFARIA_BASE}/v2/raw/index/{sefaria_name}"
        return self.get(url, cache_key=f"index_{sefaria_name}")

    def fetch_chapter(self, sefaria_name: str, chapter: int) -> Optional[dict]:
        """מביא פרק תורה שלם (פסוקי מקרא בלבד — לא פירושים)."""
        ref       = f"{sefaria_name}.{chapter}"
        cache_key = ref.replace(" ", "_")
        url       = f"{SEFARIA_BASE}/texts/{requests.utils.quote(ref)}"
        return self.get(url, cache_key=cache_key)

    def fetch_verse_commentary(self, commentary: str, sefaria_name: str,
                               chapter: int, verse: int) -> Optional[dict]:
        """
        מביא פירוש לפסוק בודד ברמת פסוק — הדרך המדויקת ב-Sefaria.
        commentary: "Rashi on" | "Ramban on"
        דוגמה: fetch_verse_commentary("Rashi on", "Bereishit", 1, 4)
               → GET /api/texts/Rashi%20on%20Bereishit.1.4
        """
        ref       = f"{commentary} {sefaria_name}.{chapter}.{verse}"
        cache_key = ref.replace(" ", "_")
        url       = f"{SEFARIA_BASE}/texts/{requests.utils.quote(ref)}"
        return self.get(url, cache_key=cache_key)


# ════════════════════════════════════════════════════════════════════════════════
# עיבוד ספר
# ════════════════════════════════════════════════════════════════════════════════

def get_chapter_count(client: SefariaClient, book: dict) -> int:
    """מחזיר מספר פרקים בספר לפי index API."""
    index = client.fetch_index(book["sefaria"])
    if index and "lengths" in index:
        # lengths[0] = מספר פרקים, lengths[1] = מספר פסוקים (תוצאה שטוחה)
        return index["lengths"][0]
    # fallback ידני (מספרים ידועים)
    fallback = {
        "Bereishit": 50, "Shemot": 40, "Vayikra": 27,
        "Bamidbar": 36, "Devarim": 34,
    }
    count = fallback.get(book["sefaria"], 0)
    if count:
        log.warning("Using fallback chapter count %d for %s", count, book["sefaria"])
    else:
        log.error("Cannot determine chapter count for %s", book["sefaria"])
    return count


def extract_verse_list(chapter_data: dict) -> list[str]:
    """מחלץ רשימת פסוקים (אנגלית או עברית) מתגובת API."""
    # Sefaria מחזיר text=[] לאנגלית, he=[] לעברית
    # לעיתים text הוא מחרוזת בודדת לפרק יחיד — נהפוך ל-list
    result = chapter_data.get("text", []) or []
    if isinstance(result, str):
        result = [result]
    return result


def extract_he_list(chapter_data: dict) -> list[str]:
    result = chapter_data.get("he", []) or []
    if isinstance(result, str):
        result = [result]
    return result


def process_book(book: dict, client: SefariaClient,
                 pbar_books: tqdm) -> dict:
    """
    מעבד ספר אחד: מוריד פסוקים + פירושים פרק-פרק.
    מחזיר dict עם מפתח "verses" שהוא רשימת כל פסוקי הספר.
    """
    sname   = book["sefaria"]
    log.info("Starting book: %s", sname)

    n_chapters = get_chapter_count(client, book)
    if not n_chapters:
        log.error("Skipping %s — chapter count unknown", sname)
        return {}

    all_verses: list[dict] = []
    missing_rashi:  list[str] = []
    missing_ramban: list[str] = []

    pbar_ch = tqdm(
        range(1, n_chapters + 1),
        desc=f"  {sname:<12} chapters",
        unit="ch",
        leave=False,
        colour="cyan",
    )

    for ch_num in pbar_ch:
        pbar_ch.set_postfix(chapter=ch_num)

        # ── 1. פסוקי תורה (ברמת פרק — מהיר ומדויק) ──────────────────────────
        text_data = client.fetch_chapter(sname, ch_num)
        if not text_data:
            log.warning("Skipping %s ch.%d — fetch failed", sname, ch_num)
            continue

        verses_en = extract_verse_list(text_data)
        verses_he = extract_he_list(text_data)
        n_verses  = max(len(verses_en), len(verses_he))

        # ── 2-4. פירושים ברמת פסוק + בנייה פסוק-לפסוק ───────────────────────
        # הסיבה: Sefaria מחזיר פירושים לפי מספור פנימי שלהם (לא לפי מספר פסוק),
        # לכן שליפה ברמת פרק אינה מיפוי נכון. שליפת פסוק בודד היא המדויקת.
        for v_idx in range(n_verses):
            v_num    = v_idx + 1
            verse_id = f"{sname}.{ch_num}.{v_num}"

            # טקסט פסוק
            en_raw = verses_en[v_idx] if v_idx < len(verses_en) else ""
            he_raw = verses_he[v_idx] if v_idx < len(verses_he) else ""

            # רש"י — שליפה ברמת פסוק
            rashi_data    = client.fetch_verse_commentary("Rashi on",  sname, ch_num, v_num) or {}
            rashi_text_en = join_commentary_verse(rashi_data.get("text"))
            rashi_text_he = join_commentary_verse(rashi_data.get("he"))
            if not rashi_text_en and not rashi_text_he:
                missing_rashi.append(verse_id)

            # רמב"ן — שליפה ברמת פסוק
            ramban_data    = client.fetch_verse_commentary("Ramban on", sname, ch_num, v_num) or {}
            ramban_text_en = join_commentary_verse(ramban_data.get("text"))
            ramban_text_he = join_commentary_verse(ramban_data.get("he"))
            if not ramban_text_en and not ramban_text_he:
                missing_ramban.append(verse_id)

            verse_obj = {
                "verse_id":      verse_id,
                "book":          sname,
                "book_he":       book["he"],
                "book_en":       book["en"],
                "book_num":      book["num"],
                "chapter":       ch_num,
                "verse":         v_num,
                "text_en":       clean_html(en_raw) if isinstance(en_raw, str) else join_commentary_verse(en_raw),
                "text_he":       clean_html(he_raw) if isinstance(he_raw, str) else join_commentary_verse(he_raw),
                "text_he_normalized": normalize_hebrew(
                    clean_html(he_raw) if isinstance(he_raw, str) else join_commentary_verse(he_raw)
                ),
                "rashi": {
                    "source_id":  f"Rashi on {verse_id}",
                    "source_url": f"https://www.sefaria.org/Rashi_on_{sname}.{ch_num}.{v_num}",
                    "text_en":    rashi_text_en,
                    "text_he":    rashi_text_he,
                    "text_he_normalized": normalize_hebrew(rashi_text_he),
                    "has_content": bool(rashi_text_en or rashi_text_he),
                },
                "ramban": {
                    "source_id":  f"Ramban on {verse_id}",
                    "source_url": f"https://www.sefaria.org/Ramban_on_{sname}.{ch_num}.{v_num}",
                    "text_en":    ramban_text_en,
                    "text_he":    ramban_text_he,
                    "text_he_normalized": normalize_hebrew(ramban_text_he),
                    "has_content": bool(ramban_text_en or ramban_text_he),
                },
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            all_verses.append(verse_obj)

    pbar_ch.close()

    # ── דוח על חסרים ──────────────────────────────────────────────────────────
    log.info(
        "%s: %d verses | Rashi missing: %d | Ramban missing: %d",
        sname, len(all_verses), len(missing_rashi), len(missing_ramban)
    )
    if missing_ramban:
        # רמב"ן לא מפרש כל פסוק — נורמלי לחלוטין
        log.debug("Ramban not on: %s", ", ".join(missing_ramban[:10]))

    result = {
        "book":            sname,
        "book_he":         book["he"],
        "book_en":         book["en"],
        "book_num":        book["num"],
        "total_verses":    len(all_verses),
        "missing_rashi":   missing_rashi,
        "missing_ramban":  missing_ramban,
        "fetched_at":      datetime.now(timezone.utc).isoformat(),
        "verses":          all_verses,
    }

    pbar_books.set_postfix(book=sname, verses=len(all_verses))
    return result


# ════════════════════════════════════════════════════════════════════════════════
# שמירה ודוח
# ════════════════════════════════════════════════════════════════════════════════

def save_book(book_data: dict, out_dir: Path) -> Path:
    """שומר ספר ל-JSON; מחזיר נתיב הקובץ."""
    fname = book_data["book"].lower() + ".json"
    out   = out_dir / fname
    out.write_text(
        json.dumps(book_data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    size_kb = out.stat().st_size / 1024
    log.info("Saved: %s (%.1f KB)", out.name, size_kb)
    return out


def print_summary(results: list[dict]) -> None:
    """מדפיס דוח סופי."""
    print("\n" + "═" * 60)
    print("  📊  Chavruta.AI — Sefaria Fetch Summary")
    print("═" * 60)
    total_v = total_r = total_rb = 0
    for r in results:
        v  = r.get("total_verses", 0)
        mr = len(r.get("missing_rashi",  []))
        mb = len(r.get("missing_ramban", []))
        rashi_pct  = 100 * (v - mr)  / v if v else 0
        ramban_pct = 100 * (v - mb)  / v if v else 0
        print(f"  {r['book_he']:>5}  {r['book']:<12}  "
              f"פסוקים: {v:>4}  |  "
              f"רש\"י: {rashi_pct:>5.1f}%  |  "
              f"רמב\"ן: {ramban_pct:>5.1f}%")
        total_v  += v
        total_r  += mr
        total_rb += mb

    print("─" * 60)
    print(f"  {'סה\"כ':<18}  פסוקים: {total_v:>4}  |  "
          f"חסרי רש\"י: {total_r}  |  חסרי רמב\"ן: {total_rb}")
    print("  (הערה: רמב\"ן אינו מפרש כל פסוק — חסרים הם נורמליים)")
    print("═" * 60 + "\n")


# ════════════════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="מוריד חמישה חומשי תורה + רש\"י + רמב\"ן מ-Sefaria API"
    )
    p.add_argument(
        "--books", nargs="+",
        choices=[b["sefaria"] for b in BOOKS],
        help="ספרים להורדה (ברירת מחדל: כולם)",
    )
    p.add_argument(
        "--clear-cache", action="store_true",
        help="מחיקת cache לפני הורדה",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="מדפיס תוכנית בלבד, לא מוריד",
    )
    p.add_argument(
        "--delay", type=float, default=REQUEST_DELAY,
        help=f"שניות בין קריאות API (ברירת מחדל: {REQUEST_DELAY})",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # בחירת ספרים
    books_to_fetch = (
        [b for b in BOOKS if b["sefaria"] in args.books]
        if args.books else BOOKS
    )

    print(f"\n{'═'*60}")
    print("  📖  Chavruta.AI — Sefaria Fetcher")
    print(f"{'═'*60}")
    print(f"  ספרים:   {', '.join(b['sefaria'] for b in books_to_fetch)}")
    print(f"  פלט:     {DATA_RAW}")
    print(f"  Delay:   {args.delay}s  |  Max retries: {MAX_RETRIES}")
    print(f"{'═'*60}\n")

    if args.dry_run:
        print("  [DRY RUN] לא מוריד. יוצא.")
        return

    # יצירת תיקיות
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    client = SefariaClient(cache_dir=CACHE_DIR, delay=args.delay)

    if args.clear_cache:
        client.clear_cache()

    results: list[dict] = []

    pbar_books = tqdm(
        books_to_fetch,
        desc="Books",
        unit="book",
        colour="green",
    )

    for book in pbar_books:
        pbar_books.set_description(f"Book: {book['sefaria']}")
        try:
            book_data = process_book(book, client, pbar_books)
            if book_data:
                save_book(book_data, DATA_RAW)
                results.append(book_data)
        except KeyboardInterrupt:
            log.warning("Interrupted by user. Partial results saved.")
            break
        except Exception as e:
            log.error("Unexpected error processing %s: %s", book["sefaria"], e, exc_info=True)
            continue

    pbar_books.close()
    print_summary(results)
    log.info("Done. Output: %s", DATA_RAW)


if __name__ == "__main__":
    main()
