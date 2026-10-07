"""app/search_service.py — Dedicated lightweight SQLite FTS5 search service for Chavruta.AI.

Runs independently on port 8081.
Provides fast full-text search across the 2.4M-chunk Jewish bookshelf corpus
with canonical ordering, language isolation, facet aggregation, and rate limiting.
"""

from __future__ import annotations

import asyncio
import os
import re
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Ensure project root is in sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chavruta.corpus.normalize import deuphemize_he, normalize_he
from chavruta.corpus.source_lookup import SourceIndex, parse as parse_source
from chavruta.intents.hebrew_refs import HE_TRACTATES
from chavruta.corpus.refs import (
    canonical_ref,
    commentator_title,
    daf_amud_to_corpus_n,
    with_ref_variants,
)

# ── Environment & Config ──────────────────────────────────────────────────────
SEARCH_DB_PATH = os.environ.get("SEARCH_DB_PATH", "data/search_index.db")
LINKS_DB_PATH = os.environ.get("LINKS_DB_PATH", "data/links_corpus.db")
SEARCH_RATE_LIMIT_PER_MINUTE = int(os.environ.get("SEARCH_RATE_LIMIT_PER_MINUTE", "120"))
TRUSTED_PROXY_HOPS = int(os.environ.get("CHAVRUTA_TRUSTED_PROXY_HOPS", "1"))

app = FastAPI(
    title="Chavruta Search Service",
    description="Fast, grounded lexical search over the Jewish bookshelf using SQLite FTS5",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ───────────────────────────────────────────────────────────────────
class SearchHit(BaseModel):
    ref: str
    book: str
    author_he: str = ""
    work_id: str
    snippet: str
    text_he: str = ""
    text_en: str | None = None
    license_he: str = ""
    license_en: str | None = None
    version_he: str = ""
    version_en: str | None = None
    category_path: str = ""
    ref_he: str = ""            # the citation in Hebrew ('תוספתא ביכורים ב׳, י׳')
    category_he: str = ""       # category_path in Hebrew
    era: str = ""               # time period: tanakh, chazal, geonim, rishonim, acharonim, modern, other


class SearchResponse(BaseModel):
    query: str
    lang: str  # "he" | "en"
    total: int
    offset: int
    limit: int
    hits: list[SearchHit]
    facets: dict[str, int]
    eras: dict[str, int] = {}     # matches per time period: tanakh, chazal, geonim, rishonim, acharonim, modern, other


class ReaderSegment(BaseModel):
    ref: str
    ref_he: str = ""      # 'בראשית א, א' — the citation in Hebrew, next to the Hebrew text
    ref_en: str = ""      # 'Genesis 1:1' — the citation in English, next to the English text
    text_he: str = ""
    text_en: str | None = None
    segment_num: int
    verse_num: int | None = None
    license_he: str = ""
    license_en: str | None = None
    version_he: str = ""
    version_en: str | None = None


class ReaderUnitResponse(BaseModel):
    ref: str
    book: str
    book_he: str = ""
    section_name: str = ""
    author_he: str = ""
    category_path: str = ""
    work_id: str = ""
    segments: list[ReaderSegment]
    prev_ref: str | None = None
    next_ref: str | None = None


class ReaderLinkItem(BaseModel):
    ref: str
    ref_he: str = ""
    source_ref: str = ""
    category: str = ""
    type: str = ""
    author_he: str = ""
    book: str = ""
    text_he: str | None = None
    text_en: str | None = None


class ReaderLinksResponse(BaseModel):
    ref: str
    commentaries: list[ReaderLinkItem]
    related: list[ReaderLinkItem]
    parallels: list[ReaderLinkItem] = []


# ── Rate Limiter ──────────────────────────────────────────────────────────────
class SlidingWindowRateLimiter:
    """Thread-safe in-memory sliding window rate limiter."""

    def __init__(self, max_requests: int, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        self._last_sweep = time.monotonic()

    def allow(self, key: str) -> bool:
        if self.max_requests <= 0:
            return True

        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            # Periodic sweep of idle keys
            if now - self._last_sweep > 300:
                self._last_sweep = now
                self._sweep(cutoff)

            hits = [t for t in self._hits.get(key, []) if t > cutoff]
            if len(hits) >= self.max_requests:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            return True

    def _sweep(self, cutoff: float) -> None:
        to_del = [k for k, v in self._hits.items() if not any(t > cutoff for t in v)]
        for k in to_del:
            del self._hits[k]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


_rate_limiter = SlidingWindowRateLimiter(SEARCH_RATE_LIMIT_PER_MINUTE, 60.0)


def _get_client_key(request: Request) -> str:
    """Identify the caller by proxy-derived client IP only.

    This service has no auth, so client-supplied identity headers (X-User-ID,
    a Bearer token) are NOT used: a caller could rotate them freely to get a
    fresh rate-limit bucket per request.
    """
    peer = request.client.host if request.client else "127.0.0.1"
    if TRUSTED_PROXY_HOPS <= 0:
        return f"ip:{peer}"

    fwd = request.headers.get("x-forwarded-for")
    if not fwd:
        return f"ip:{peer}"

    parts = [p.strip() for p in fwd.split(",") if p.strip()]
    if len(parts) >= TRUSTED_PROXY_HOPS:
        return f"ip:{parts[-TRUSTED_PROXY_HOPS]}"
    return f"ip:{peer}"


# ── Database Connection ───────────────────────────────────────────────────────
_db_connection: sqlite3.Connection | None = None
_db_lock = threading.Lock()


def get_db_path() -> str:
    return os.environ.get("SEARCH_DB_PATH", SEARCH_DB_PATH)


def get_db() -> sqlite3.Connection:
    global _db_connection
    path = get_db_path()
    if not Path(path).exists():
        raise HTTPException(
            status_code=503,
            detail=f"Search database not found at {path}. Run scripts/build_search_index.py first.",
        )

    with _db_lock:
        if _db_connection is None:
            # Read-only SQLite connection
            uri = f"file:{Path(path).resolve().as_posix()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            _load_layer_rank(conn)
            _db_connection = conn
        return _db_connection


_links_db_connection: sqlite3.Connection | None = None
_links_db_lock = threading.Lock()


def get_links_db_path() -> str:
    return os.environ.get("LINKS_DB_PATH", LINKS_DB_PATH)


def get_links_db() -> sqlite3.Connection | None:
    global _links_db_connection
    path = get_links_db_path()
    if not Path(path).exists():
        return None

    with _links_db_lock:
        if _links_db_connection is None:
            uri = f"file:{Path(path).resolve().as_posix()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            _links_db_connection = conn
        return _links_db_connection


def close_links_db() -> None:
    global _links_db_connection
    with _links_db_lock:
        if _links_db_connection is not None:
            _links_db_connection.close()
            _links_db_connection = None


def close_db() -> None:
    global _db_connection
    with _db_lock:
        if _db_connection is not None:
            _db_connection.close()
            _db_connection = None
    close_links_db()


def strip_nikud(text: str) -> str:
    """Remove Hebrew vowel points and cantillation marks, keeping authentic letters and punctuation."""
    if not text:
        return ""
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))


def generate_clean_snippet(
    full_text: str,
    raw_query: str,
    is_he: bool = True,
    max_words: int = 32,
) -> str:
    """Generate clean snippet using authentic source text without spelling distortions and WITHOUT leading/trailing dots."""
    if not full_text:
        return ""

    # Clean text: strip nikud for display without altering letters or punctuation
    clean_text = strip_nikud(full_text) if is_he else full_text
    words = clean_text.split()
    if not words:
        return ""

    # Extract query terms
    raw_terms = [t.strip().strip('"').strip("'") for t in raw_query.split() if t.strip()]
    terms = [strip_nikud(t) for t in raw_terms if strip_nikud(t)]

    # Build regex patterns for matching words
    patterns: list[str] = []
    for t in terms:
        t_esc = re.escape(t)
        patterns.append(rf"(?:^[וכלבמשה])?{t_esc}")

    combined_re = re.compile(rf"(?:{'|'.join(patterns)})", re.IGNORECASE) if patterns else None

    # Find position of best match
    best_idx = 0
    if combined_re:
        for i, w in enumerate(words):
            w_strip = re.sub(r"[^\w\u0590-\u05FF]", "", w)
            if combined_re.search(w_strip):
                best_idx = i
                break

    # Window around best_idx
    half = max_words // 2
    start_idx = max(0, best_idx - half)
    end_idx = min(len(words), start_idx + max_words)
    if end_idx - start_idx < max_words:
        start_idx = max(0, end_idx - max_words)

    snippet_words = words[start_idx:end_idx]

    # Highlight matching words with <mark>...</mark>
    result_words = []
    for w in snippet_words:
        w_strip = re.sub(r"[^\w\u0590-\u05FF]", "", w)
        if combined_re and combined_re.search(w_strip):
            m_punct = re.match(r"^([^\w\u0590-\u05FF]*)(.*?)([^\w\u0590-\u05FF]*)$", w)
            if m_punct:
                pre, core, post = m_punct.groups()
                result_words.append(f"{pre}<mark>{core}</mark>{post}")
            else:
                result_words.append(f"<mark>{w}</mark>")
        else:
            result_words.append(w)

    # Join without leading or trailing dots
    return " ".join(result_words)


# ── Search Utilities ──────────────────────────────────────────────────────────
def has_hebrew_majority(q: str) -> bool:
    """Determine if query is predominantly Hebrew."""
    he_count = sum(1 for ch in q if "\u0590" <= ch <= "\u05ff")
    en_count = sum(1 for ch in q if ("a" <= ch <= "z") or ("A" <= ch <= "Z"))
    if he_count == 0 and en_count == 0:
        return False
    return he_count >= en_count


def escape_fts5_query(term: str, is_he: bool = False) -> str:
    """Escape tokens for safe FTS5 MATCH query syntax.

    For Hebrew, expands divine name variants between plene and defective spellings
    (e.g., אלוהים and אלהים) so that reverent queries like אלוקים match both.
    """
    term = term.strip()
    if not term:
        return ""

    tokens = [t.replace('"', '""') for t in term.split() if t.strip()]
    if not tokens:
        return ""

    parts: list[str] = []
    for t in tokens:
        # ``t`` already has embedded quotes doubled; every emitted token is
        # wrapped in double quotes so FTS5 treats it as a literal string.
        if is_he:
            if "אלוה" in t:
                alt = t.replace("אלוה", "אלה")
                parts.append(f'("{t}" OR "{alt}")')
                continue
            elif "אלה" in t and any(t.startswith(p + "אלה") for p in ("", "ב", "כ", "ל", "מ", "ש", "ה", "ו", "ד")):
                if any(t.endswith(suf) for suf in ("ימ", "י", "ינו", "יכמ", "יהמ", "יכ")):
                    alt = t.replace("אלה", "אלוה", 1)
                    parts.append(f'("{t}" OR "{alt}")')
                    continue
        parts.append(f'"{t}"')

    # Explicit AND: FTS5 rejects implicit AND next to a parenthesised group,
    # so `("a" OR "b") "c"` is a syntax error while `("a" OR "b") AND "c"` is not.
    return " AND ".join(parts)


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    db_ok = Path(get_db_path()).exists()
    return {
        "status": "ok",
        "database": "ready" if db_ok else "missing",
        "database_path": get_db_path(),
    }


# ── Content-search ordering ───────────────────────────────────────────────────
# Results come back in the order a learner meets the sources, not alphabetically: Tanakh (Torah,
# Prophets, Writings), then Chazal (Mishnah, Tosefta, Gemara, Midrash), then the commentators and later
# literature by THEIR era — a Rishon beside the Rishonim, an Acharon beside the Acharonim. The rank of
# each category comes from data/layer_rank.json (scripts/build_layer_rank.py); ties fall back to `rowid`,
# the load order, which is canonical inside a book (Genesis → Deuteronomy, verses and dapim in sequence).
_LAYER_RANK_PATH = Path(__file__).resolve().parent.parent / "src" / "chavruta" / "corpus" / "data" / "layer_rank.json"
_UNRANKED = 800        # rows with no category (e.g. the Hebrew-Wikisource additions) go after the ranked works


# the time period of a row, from its layer rank (scripts/build_layer_rank.py: <20 Tanakh, <200 Chazal, 2xx Geonim ...)
_ERA_SQL = (
    "CASE WHEN COALESCE(lr.rank, 800) < 20 THEN 'tanakh' WHEN lr.rank < 200 THEN 'chazal' WHEN lr.rank < 300 THEN 'geonim' "
    "WHEN lr.rank < 400 THEN 'rishonim' WHEN lr.rank < 500 THEN 'acharonim' WHEN lr.rank < 800 THEN 'modern' ELSE 'other' END"
)


def _load_layer_rank(conn: sqlite3.Connection) -> None:
    """Put the ranks in a TEMP table of this connection, so the ordering is a join and the read-only
    database file is never touched."""
    import json
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS layer_rank (category_path TEXT PRIMARY KEY, rank INTEGER)")
    try:
        ranks = json.loads(_LAYER_RANK_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ranks = {}
    conn.executemany("INSERT OR REPLACE INTO layer_rank VALUES (?, ?)", list(ranks.items()))


@app.get("/search/query", response_model=SearchResponse)
async def search_query(
    request: Request,
    q: str = Query(..., min_length=1, description="Search query string"),
    offset: int = Query(0, ge=0, le=10000, description="Offset for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Number of results per page"),
    work_id: str | None = Query(None, description="Optional work_id filter, comma-separated"),
    era: str | None = Query(None, max_length=120, description="Optional time-period filter, comma-separated (tanakh, chazal, geonim, rishonim, acharonim, modern, other)"),
    book: str | None = Query(None, max_length=200, description="Optional: search inside one book (its English title)"),
):
    # 0. Rate limiting (120 req/min)
    client_key = _get_client_key(request)
    if not _rate_limiter.allow(client_key):
        return JSONResponse(
            status_code=429,
            content={"detail": "rate limit exceeded — please slow down"},
            headers={"Retry-After": "60"},
        )

    # 1. Language detection
    is_he = has_hebrew_majority(q)
    lang = "he" if is_he else "en"

    # 2. Normalization
    if is_he:
        normalized_q = normalize_he(deuphemize_he(q))
        fts_col = "search_he"
        col_idx = 0
    else:
        normalized_q = q.lower().strip()
        fts_col = "search_en"
        col_idx = 1

    if not normalized_q:
        return SearchResponse(
            query=q,
            lang=lang,
            total=0,
            offset=offset,
            limit=limit,
            hits=[],
            facets={},
        )

    # 3. FTS5 query formulation
    escaped_tokens = escape_fts5_query(normalized_q, is_he=is_he)
    if not escaped_tokens:
        return SearchResponse(
            query=q,
            lang=lang,
            total=0,
            offset=offset,
            limit=limit,
            hits=[],
            facets={},
        )

    # Parenthesised so the column filter covers every token, not just the first.
    match_expr = f"{fts_col}: ({escaped_tokens})"

    # 4. Filter clause for work_id
    work_ids: list[str] = []
    if work_id:
        work_ids = [w.strip().lower() for w in work_id.split(",") if w.strip()]

    # Connect to database
    db = get_db()

    # Inside one book: its rows carry the title in `book` — exactly, or as "<title>, <section>" for the
    # works whose sections are recorded in the book name.
    book_sql, book_params = "", []
    if book and book.strip():
        book_sql = " AND (c.book = ? OR c.book LIKE ? ESCAPE '\\')"
        book_params = [book.strip(), like_escape(book.strip()) + ", %"]

    eras_wanted = [e.strip().lower() for e in (era or "").split(",") if e.strip()]

    # 5. Facet counts aggregation (computed on all matches matching language and query), by work and by period
    facets_sql = f"""
        SELECT c.work_id, {_ERA_SQL} AS era, COUNT(*) as cnt
        FROM search_fts f
        JOIN chunks c ON c.rowid = f.rowid
        LEFT JOIN layer_rank lr ON lr.category_path = c.category_path
        WHERE search_fts MATCH ?{book_sql}
        GROUP BY c.work_id, era
    """
    facet_rows = db.execute(facets_sql, (match_expr, *book_params)).fetchall()
    facets: dict[str, int] = {}
    eras: dict[str, int] = {}
    total = 0
    for row in facet_rows:
        facets[row["work_id"]] = facets.get(row["work_id"], 0) + row["cnt"]
        eras[row["era"]] = eras.get(row["era"], 0) + row["cnt"]
        # total of the hits that pass the work and period filters
        if (not work_ids or row["work_id"].lower() in work_ids) and (not eras_wanted or row["era"] in eras_wanted):
            total += row["cnt"]

    # 6. Fetch paginated search hits
    params: list[Any] = [match_expr, *book_params]
    where_extra = ""
    if work_ids:
        placeholders = ",".join("?" for _ in work_ids)
        where_extra = f"AND LOWER(c.work_id) IN ({placeholders})"
        params.extend(work_ids)
    if eras_wanted:
        where_extra += f" AND {_ERA_SQL} IN ({','.join('?' for _ in eras_wanted)})"
        params.extend(eras_wanted)

    query_sql = f"""
        SELECT c.ref,
               c.book,
               c.author_he,
               c.work_id,
               snippet(search_fts, {col_idx}, '<mark>', '</mark>', '…', 30) as snippet,
               c.text_he,
               c.text_en,
               c.license_he,
               c.license_en,
               c.version_he,
               c.version_en,
               c.category_path,
               {_ERA_SQL} AS era
        FROM search_fts f
        JOIN chunks c ON c.rowid = f.rowid
        LEFT JOIN layer_rank lr ON lr.category_path = c.category_path
        WHERE search_fts MATCH ?{book_sql}
        {where_extra}
        ORDER BY COALESCE(lr.rank, {_UNRANKED}), c.rowid
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    rows = db.execute(query_sql, params).fetchall()

    hits: list[SearchHit] = []
    for r in rows:
        base_text = r["text_he"] if is_he else (r["text_en"] or "")
        snip = generate_clean_snippet(base_text, q, is_he=is_he)

        hits.append(
            SearchHit(
                ref=r["ref"] or "",
                book=r["book"] or "",
                author_he=r["author_he"] or "",
                work_id=r["work_id"] or "",
                snippet=snip,
                text_he=r["text_he"] or "",
                text_en=r["text_en"],
                license_he=r["license_he"] or "",
                license_en=r["license_en"],
                version_he=r["version_he"] or "",
                version_en=r["version_en"],
                category_path=r["category_path"] or "",
                ref_he=ref_labels(r["ref"] or "")[0],
                category_he=category_labels(r["category_path"] or ""),
                era=r["era"],
            )
        )

    return SearchResponse(
        query=q,
        lang=lang,
        total=total,
        offset=offset,
        limit=limit,
        hits=hits,
        facets=facets,
        eras=eras,
    )


# ── Reader Utilities ──────────────────────────────────────────────────────────
KNOWN_AUTHORS_HE: dict[str, str] = {
    "rashi": "רש\"י",
    "ramban": "רמב\"ן",
    "rashbam": "רשב\"ם",
    "ibn ezra": "אבן עזרא",
    "sforno": "ספורנו",
    "tosafot": "תוספות",
    "ba'al haturim": "בעל הטורים",
    "or hachaim": "אור החיים",
    "radak": "רד\"ק",
    "ralbag": "רלב\"ג",
    "malbim": "מלבי\"ם",
    "metzudat david": "מצודת דוד",
    "metzudat zion": "מצודת ציון",
    "chizkuni": "חזקוני",
    "onkelos": "אונקלוס",
    "targum": "תרגום",
    "meiri": "מאירי",
    "ritva": "ריטב\"א",
    "rashba": "רשב\"א",
    "ran": "ר\"ן",
    "rosh": "רא\"ש",
    "mordechai": "מרדכי",
    "bartenura": "ברטנורא",
    "tosafot yom tov": "תוספות יום טוב",
}


def extract_segment_num(ref: str, fallback: int) -> int:
    m = re.search(r"[:. ](\d+)$", (ref or "").strip())
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return fallback


def compute_prev_next_unit(raw_ref: str) -> tuple[str | None, str | None]:
    ref = (raw_ref or "").strip()
    m_sub = re.match(r"^(.*?)(?::\d+)+$", ref)
    if m_sub:
        ref = m_sub.group(1).strip()

    m = re.match(r"^(.*?)([ ._])(\d+)([ab]?)$", ref, re.IGNORECASE)
    if not m:
        return None, None
    book_part = m.group(1)
    sep = m.group(2)
    num_str = m.group(3)
    amud = m.group(4).lower()

    if amud in ("a", "b"):
        daf = int(num_str)
        if amud == "a":
            prev_ref = f"{book_part}{sep}{daf - 1}b" if daf > 2 else None
            next_ref = f"{book_part}{sep}{daf}b"
        else:
            prev_ref = f"{book_part}{sep}{daf}a"
            next_ref = f"{book_part}{sep}{daf + 1}a"
        return prev_ref, next_ref
    else:
        num = int(num_str)
        prev_ref = f"{book_part}{sep}{num - 1}" if num > 1 else None
        next_ref = f"{book_part}{sep}{num + 1}"
        return prev_ref, next_ref


# Hard cap on rows a single /reader/unit call may return. A real unit (a
# chapter, an amud, a siman) is at most a few hundred segments; the cap only
# bites on a pathological ref and keeps one request from materialising a
# large slice of the 2.4M-row table on a blocking worker.
READER_UNIT_MAX_ROWS = 5000


def like_escape(value: str) -> str:
    """Escape LIKE metacharacters so ``value`` matches literally.

    Use with ``LIKE ? ESCAPE '\\'``. Caller text such as ``_`` or ``%``
    would otherwise act as a wildcard and match the whole table.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def get_unit_query_prefixes(clean_ref: str) -> list[str]:
    """Literal (unescaped) ref prefixes for a unit; callers must ``like_escape`` them."""
    clean = clean_ref.strip()
    prefixes: list[str] = []

    m_sub = re.match(r"^(.*?)[ ._](\d+[ab]?)(?::\d+)+$", clean, re.IGNORECASE)
    if m_sub:
        parent_candidate = f"{m_sub.group(1)} {m_sub.group(2)}"
        prefixes.extend(get_unit_query_prefixes(parent_candidate))

    m = re.match(r"^(.*?)[ ._](\d+[ab]?)$", clean, re.IGNORECASE)
    if m:
        book_raw = m.group(1).strip()
        unit = m.group(2).strip()

        book_space = book_raw.replace("_", " ")
        book_under = book_raw.replace(" ", "_")
        books = list(dict.fromkeys([book_raw, book_space, book_under]))

        for b in books:
            prefixes.append(f"{b} {unit}:")
            prefixes.append(f"{b} {unit}.")
            prefixes.append(f"{b}.{unit}.")
            prefixes.append(f"{b}.{unit}:")
            prefixes.append(f"{b}_{unit}_")
            prefixes.append(f"{b}_{unit}.")
            prefixes.append(f"{b} {unit} ")

        m_amud = re.match(r"^(\d+)([ab])$", unit, re.IGNORECASE)
        if m_amud:
            daf = int(m_amud.group(1))
            amud = m_amud.group(2).lower()
            corpus_n = daf_amud_to_corpus_n(daf, amud)
            for b in books:
                prefixes.append(f"{b} {corpus_n}:")
                prefixes.append(f"{b} {corpus_n}.")
                prefixes.append(f"{b}.{corpus_n}.")
                prefixes.append(f"{b}_{corpus_n}_")
    else:
        prefixes.append(f"{clean}:")
        prefixes.append(f"{clean}.")
        prefixes.append(f"{clean}_")
        prefixes.append(f"{clean} ")
        prefixes.append(f"{clean.replace('_', ' ')}:")
        prefixes.append(f"{clean.replace(' ', '_')}.")

    return list(dict.fromkeys(prefixes))


def format_canon_to_ref(canon: str) -> str:
    c = (canon or "").strip()
    if not c:
        return ""
    if " on " in c:
        auth, base = c.split(" on ", 1)
        auth_title = " ".join(w.capitalize() for w in auth.split())
        base_toks = base.split()
        num_start = len(base_toks)
        while num_start > 0 and (
            base_toks[num_start - 1].isdigit()
            or re.match(r"^\d+[ab]?$", base_toks[num_start - 1])
        ):
            num_start -= 1
        book_title = " ".join(w.capitalize() for w in base_toks[:num_start])
        num_part = ":".join(base_toks[num_start:])
        return f"{auth_title} on {book_title} {num_part}" if num_part else f"{auth_title} on {book_title}"
    else:
        toks = c.split()
        num_start = len(toks)
        while num_start > 0 and (
            toks[num_start - 1].isdigit()
            or re.match(r"^\d+[ab]?$", toks[num_start - 1])
        ):
            num_start -= 1
        book_title = " ".join(w.capitalize() for w in toks[:num_start])
        num_part = ":".join(toks[num_start:])
        return f"{book_title} {num_part}" if num_part else book_title


def format_author_from_canon(canon: str) -> str:
    c = (canon or "").strip().lower()
    if " on " in c:
        auth = c.split(" on ", 1)[0].strip()
        return KNOWN_AUTHORS_HE.get(auth, commentator_title(auth))
    first_word = c.split()[0] if c else ""
    return KNOWN_AUTHORS_HE.get(first_word, "")


def format_book_from_canon(canon: str) -> str:
    c = (canon or "").strip()
    if " on " in c:
        base = c.split(" on ", 1)[1]
    else:
        base = c
    toks = base.split()
    num_start = len(toks)
    while num_start > 0 and (
        toks[num_start - 1].isdigit()
        or re.match(r"^\d+[ab]?$", toks[num_start - 1])
    ):
        num_start -= 1
    book_words = toks[:num_start] if num_start > 0 else toks
    return " ".join(w.capitalize() for w in book_words)


def canon_to_candidate_keys(canon: str) -> list[str]:
    c = (canon or "").strip()
    if not c:
        return []
    keys = [c]
    if " on " in c:
        author_part, base_part = c.split(" on ", 1)
        base_toks = base_part.split()
        num_start = len(base_toks)
        while num_start > 0 and (
            base_toks[num_start - 1].isdigit()
            or re.match(r"^\d+[ab]?$", base_toks[num_start - 1])
        ):
            num_start -= 1
        book_words = base_toks[:num_start]
        num_words = base_toks[num_start:]
        book_title = " ".join(w.capitalize() for w in book_words)
        book_under = "_".join(w.capitalize() for w in book_words)
        author_title = "_".join(w.capitalize() for w in author_part.split())
        num_dots = ".".join(num_words)
        num_colons = ":".join(num_words)
        joined_nums = "_".join(num_words)
        if num_words:
            keys.append(f"{author_title}_on_{book_under}.{num_dots}")
            keys.append(f"{author_title} on {book_title} {num_colons}")
            keys.append(f"{author_title} on {book_title} {num_dots}")
            keys.append(f"{author_part}_on_{book_under.lower()}.{num_dots}")
            keys.append(f"{author_part}_on_{book_under.lower()}_{joined_nums}")
            if len(num_words) >= 2:
                prefix_colons = ":".join(num_words[:-1])
                prefix_dots = ".".join(num_words[:-1])
                keys.append(f"{author_title} on {book_title} {prefix_colons}")
                keys.append(f"{author_title}_on_{book_under}.{prefix_dots}")
        else:
            keys.append(f"{author_title}_on_{book_under}")
            keys.append(f"{author_title} on {book_title}")
    else:
        toks = c.split()
        num_start = len(toks)
        while num_start > 0 and (
            toks[num_start - 1].isdigit()
            or re.match(r"^\d+[ab]?$", toks[num_start - 1])
        ):
            num_start -= 1
        book_words = toks[:num_start]
        num_words = toks[num_start:]
        book_title = " ".join(w.capitalize() for w in book_words)
        book_under = "_".join(w.capitalize() for w in book_words)
        num_dots = ".".join(num_words)
        num_colons = ":".join(num_words)
        joined_nums = "_".join(num_words)
        first_b = book_words[0] if book_words else ""
        if num_words:
            keys.append(f"{book_title} {num_colons}")
            keys.append(f"{book_title} {num_dots}")
            keys.append(f"{book_under}.{num_dots}")
            keys.append(f"{first_b}_{joined_nums}")
            keys.append(f"{book_title.lower()}_{joined_nums}")
        else:
            keys.append(book_title)
            keys.append(book_under)
    return list(dict.fromkeys(keys))


def to_gematria_he(num: int) -> str:
    if num <= 0:
        return str(num)
    letter_vals = [
        (400, "ת"), (300, "ש"), (200, "ר"), (100, "ק"),
        (90, "צ"), (80, "פ"), (70, "ע"), (60, "ס"),
        (50, "נ"), (40, "מ"), (30, "ל"), (20, "כ"),
        (10, "י"), (9, "ט"), (8, "ח"), (7, "ז"),
        (6, "ו"), (5, "ה"), (4, "ד"), (3, "ג"),
        (2, "ב"), (1, "א")
    ]
    n = num
    res = ""
    while n > 0:
        if n == 15:
            res += "טו"
            break
        if n == 16:
            res += "טז"
            break
        for val, char in letter_vals:
            if n >= val:
                res += char
                n -= val
                break
    if len(res) == 1:
        return res + "׳"
    elif len(res) > 1 and "״" not in res:
        return res[:-1] + "״" + res[-1]
    return res


def format_section_name(clean_ref: str) -> str:
    m_daf = re.search(r"[._ ](\d+)([ab])$", clean_ref, re.IGNORECASE)
    if m_daf:
        d_num = int(m_daf.group(1))
        amud = 'ע"א' if m_daf.group(2).lower() == 'a' else 'ע"ב'
        return f"דף {to_gematria_he(d_num)} {amud}"

    nums = re.findall(r"\b\d+\b", clean_ref)
    if not nums:
        return ""

    if len(nums) == 1:
        ch = int(nums[0])
        return f"פרק {to_gematria_he(ch)}"
    elif len(nums) >= 2:
        ch = int(nums[0])
        vs = int(nums[1])
        return f"פרק {to_gematria_he(ch)}, פסוק {to_gematria_he(vs)}"

    return ""


# ── Reader Endpoints ──────────────────────────────────────────────────────────
_CATALOG_PATH = Path(__file__).resolve().parent.parent / "src" / "chavruta" / "corpus" / "data" / "catalog.json"
_BOOK_ORDER_PATH = _CATALOG_PATH.with_name("book_order.json")   # scripts/lookup_book_order.py
_catalog_cache: bytes | None = None
_category_he: dict[str, str] | None = None             # "Tosefta/Vilna Edition" -> Hebrew name of the last part
_title_index: dict[str, tuple[str, str]] | None = None   # English title -> (Hebrew title, category path)
_REF_PARTS = re.compile(r"^(?P<title>.+?) (?P<nums>\d+(?::\d+)*)$")


def _titles() -> dict[str, tuple[str, str]]:
    global _title_index, _category_he
    if _title_index is None:
        import json
        try:
            cat = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
            books = cat["books"]
            _category_he = {k: v.get("he", "") for k, v in cat.get("categories", {}).items()}
        except (OSError, ValueError, KeyError):
            books, _category_he = [], {}
        _title_index = {b["title_en"]: (b.get("title_he") or "", b.get("path") or "") for b in books}
    return _title_index


def _is_bavli_title(title: str) -> bool:
    """A Bavli tractate or a commentary on one: their reader refs count amudim linearly (N = 2*daf -/+ 1)."""
    t = _titles()
    he_path = t.get(title, ("", ""))[1]
    if he_path.startswith("Talmud/Bavli"):
        return True
    if " on " in title and not he_path.startswith(("Tosefta", "Talmud/Yerushalmi", "Mishnah")):
        base = title.split(" on ", 1)[1]
        return t.get(base, ("", ""))[1].startswith("Talmud/Bavli")
    return False


def category_labels(path: str) -> str:
    """'Tosefta / Vilna Edition / Seder Zeraim' -> 'תוספתא / מהדורת וילנא / סדר זרעים' (unknown parts stay English)."""
    _titles()
    parts = [p for p in (path or "").split(" / ") if p]
    return " / ".join((_category_he or {}).get("/".join(parts[: i + 1])) or p for i, p in enumerate(parts))


def ref_labels(ref: str) -> tuple[str, str]:
    """(Hebrew, English) citation for a corpus display ref: 'Genesis 1:1' -> ('בראשית א, א', 'Genesis 1:1'),
    'Berakhot 3:1' -> ('ברכות ב ע״א, א', 'Berakhot 2a:1'). Falls back to the ref itself for titles the
    catalogue does not know, so a label is never empty."""
    m = _REF_PARTS.match((ref or "").strip())
    if not m:
        return ref or "", ref or ""
    title, nums = m.group("title"), [int(n) for n in m.group("nums").split(":")]
    title_he = _titles().get(title, ("", ""))[0]
    if not title_he and ", " in title:    # 'Ein Yaakov, Berakhot': work + the tractate it is cited by
        head, tail = title.rsplit(", ", 1)
        head_he, tail_he = _titles().get(head, ("", ""))[0], _titles().get(tail, ("", ""))[0]
        title_he = f"{head_he or head}, {tail_he or tail}"
    title_he = title_he or title
    en_parts = [str(n) for n in nums]
    he_parts = [to_gematria_he(n) for n in nums]
    if _is_bavli_title(title):
        daf, amud = (nums[0] + 1) // 2, ("a" if nums[0] % 2 else "b")
        en_parts[0] = f"{daf}{amud}"
        he_parts[0] = f"{to_gematria_he(daf)} {'ע״א' if amud == 'a' else 'ע״ב'}"
    return f"{title_he} {', '.join(he_parts)}", f"{title} {':'.join(en_parts)}"


@app.get("/reader/catalog")
async def reader_catalog() -> Response:
    """The library page's book list: every commercially-licensed work with its Hebrew title and
    category path. Static package data (scripts/build_catalog.py), so no database is touched and
    the response is cacheable; the client does all filtering and searching."""
    global _catalog_cache
    if _catalog_cache is None:
        import json
        try:
            cat = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise HTTPException(status_code=503, detail="Library catalogue not built (scripts/build_catalog.py).")
        try:
            ranks = json.loads(_LAYER_RANK_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            ranks = {}
        try:
            order = json.loads(_BOOK_ORDER_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            order = {}
        for b in cat.get("books", []):
            b["order"] = order.get(b["title_en"], 10**9)     # load order: Genesis -> Deuteronomy, Seder Zeraim -> ...      # learning order, so book search lists Torah before Rashi before the Malbim
            b["rank"] = ranks.get(" / ".join((b.get("path") or "").split("/")), _UNRANKED)
        _catalog_cache = json.dumps(cat, ensure_ascii=False).encode("utf-8")
    return Response(content=_catalog_cache, media_type="application/json",
                    headers={"Cache-Control": "public, max-age=300"})


def _unit_where(clean_ref: str) -> tuple[str, list[Any]]:
    """WHERE clause + params selecting the rows of one reader unit (a chapter, a daf, a siman…)."""
    clauses: list[str] = []
    params: list[Any] = []
    for p in get_unit_query_prefixes(clean_ref):
        pattern = f"{like_escape(p)}%"
        clauses.append("ref LIKE ? ESCAPE '\\'")
        params.append(pattern)
        clauses.append("chunk_id LIKE ? ESCAPE '\\'")
        params.append(pattern)
    clauses.append("ref = ?")
    params.append(clean_ref)
    clauses.append("chunk_id = ?")
    params.append(clean_ref)
    return " OR ".join(clauses), params


def _unit_exists(db: sqlite3.Connection, clean_ref: str) -> bool:
    where_sql, params = _unit_where(clean_ref)
    return db.execute(f"SELECT 1 FROM chunks WHERE {where_sql} LIMIT 1", params).fetchone() is not None


_source_index: SourceIndex | None = None


def _get_source_index() -> SourceIndex:
    global _source_index
    if _source_index is None:
        import json
        books = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))["books"]
        _source_index = SourceIndex(books)
    return _source_index


@app.get("/reader/resolve")
async def reader_resolve(request: Request, q: str = Query(..., min_length=1, max_length=120)):
    """Library source search: a typed citation ("בראשית א א", "ברכות ב ע״ב") → readable units.

    Only citations that exist in the reader's index are returned, so a link from here never 404s.
    A verse-level citation opens its whole chapter and the reader scrolls to the verse."""
    if not _rate_limiter.allow(_get_client_key(request)):
        return JSONResponse(status_code=429, content={"detail": "rate limit exceeded — please slow down"},
                            headers={"Retry-After": "60"})
    db = get_db()
    out = []
    for src in parse_source(q, _get_source_index()):
        link = None
        # The reader widens "Genesis 1:9" to the whole chapter even when verse 9 does not exist, so the
        # verse itself is checked exactly; otherwise the chapter opens without a scroll target.
        if src.target and db.execute("SELECT 1 FROM chunks WHERE ref = ? LIMIT 1", (src.target,)).fetchone():
            link = src.target
        elif _unit_exists(db, src.ref):
            link = src.ref
        if link:
            out.append({"ref": link, "book_he": src.book_he, "book_en": src.book_en, "nums": list(src.nums)})
    return {"query": q, "matches": out}


_UNIT_RE = re.compile(r"^(?P<head>.+?)\.(?P<first>\d+[ab]?)(?:\.\d+[ab]?)*$")
_toc_cache: dict[str, dict] = {}
_TOC_MAX_ROWS = 60000


def _book_units(db: sqlite3.Connection, title_en: str) -> dict:
    """The units of one book (chapters, dapim, simanim…), derived from the reader's own index.

    chunk_id is '<corpus ref>_<work_id>' and UNIQUE-indexed, so a book is two cheap prefix ranges:
    '<stem>.' (its numbered refs) and '<stem>,' (works that record a section name before the number,
    like 'Chizkuni,_Genesis.17'). A unit is a ref cut after its first number. Bavli refs are amud-linear
    (N = 2·daf ∓ 1, so Berakhot.3 is 2a and Berakhot.4 is 2b) and are turned back into dapim here.
    """
    stem = title_en.replace(" ", "_")
    is_bavli = title_en in HE_TRACTATES.values()
    ranges = [(stem + ".", stem + "/"), (stem + ",", stem + "-")]
    units: dict[tuple[str, int, str], int] = {}
    first_row: dict[str, int] = {}     # section → first rowid: rows were loaded in canonical order
    for lo, hi in ranges:
        for rowid, chunk_id, work_id in db.execute(
                "SELECT rowid, chunk_id, work_id FROM chunks WHERE chunk_id >= ? AND chunk_id < ? LIMIT ?",
                (lo, hi, _TOC_MAX_ROWS)):
            suffix = "_" + (work_id or "")
            ref = chunk_id[: -len(suffix)] if suffix != "_" and chunk_id.endswith(suffix) else chunk_id
            m = _UNIT_RE.match(ref)
            if not m:
                continue
            head, first = m.group("head"), m.group("first")
            side = ""
            if first[-1] in "ab":
                n, side = int(first[:-1]), first[-1]
            else:
                n = int(first)
                if is_bavli:
                    n, side = (n + 1) // 2, "a" if n % 2 else "b"
            key = (head, n, side)
            units[key] = units.get(key, 0) + 1
            first_row[head] = min(first_row.get(head, rowid), rowid)
    out = []
    for (head, n, side), count in sorted(units.items(), key=lambda kv: (first_row[kv[0][0]], kv[0][1], kv[0][2])):
        section = head[len(stem) + 1:] if head.startswith(stem + ",") else ""
        out.append({"ref": f"{head}.{n}{side}", "section": section.lstrip("_").replace("_", " "),
                    "n": n, "side": side, "count": count})
    return {"book": title_en, "kind": "daf" if is_bavli else "chapter", "units": out}


@app.get("/reader/toc")
async def reader_toc(request: Request, book: str = Query(..., min_length=1, max_length=200)):
    """Table of contents for the library's book page: the chapters / dapim a book actually has."""
    if not _rate_limiter.allow(_get_client_key(request)):
        return JSONResponse(status_code=429, content={"detail": "rate limit exceeded — please slow down"},
                            headers={"Retry-After": "60"})
    title = book.strip()
    if title not in _toc_cache:
        data = _book_units(get_db(), title)
        if not data["units"]:
            raise HTTPException(status_code=404, detail=f"No units for: {title}")
        if len(_toc_cache) > 512:
            _toc_cache.clear()
        _toc_cache[title] = data
    return JSONResponse(_toc_cache[title], headers={"Cache-Control": "public, max-age=3600"})


@app.get("/reader/unit", response_model=ReaderUnitResponse)
async def reader_unit(
    request: Request,
    ref: str = Query(
        ...,
        min_length=1,
        description="Unit reference (e.g. Genesis.1, Berakhot.2a, Shulchan_Arukh,_Orach_Chayim.263)",
    ),
):
    # 0. Rate limiting (120 req/min)
    client_key = _get_client_key(request)
    if not _rate_limiter.allow(client_key):
        return JSONResponse(
            status_code=429,
            content={"detail": "rate limit exceeded — please slow down"},
            headers={"Retry-After": "60"},
        )

    clean_ref = ref.strip()
    if not clean_ref:
        raise HTTPException(status_code=404, detail="Unit not found")
    db = get_db()
    where_sql, params = _unit_where(clean_ref)
    query_sql = f"""
        SELECT rowid, chunk_id, ref, book, author_he, work_id, category_path,
               text_he, text_en, license_he, license_en, version_he, version_en
        FROM chunks
        WHERE {where_sql}
        ORDER BY rowid ASC
        LIMIT ?
    """
    params.append(READER_UNIT_MAX_ROWS)
    rows = db.execute(query_sql, params).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail=f"Unit not found: {clean_ref}")

    segments: list[ReaderSegment] = []
    for idx, r in enumerate(rows):
        seg_num = extract_segment_num(r["ref"] or "", idx + 1)
        ref_he, ref_en = ref_labels(r["ref"] or "")
        segments.append(
            ReaderSegment(
                ref=r["ref"] or "",
                ref_he=ref_he,
                ref_en=ref_en,
                text_he=r["text_he"] or "",
                text_en=r["text_en"],
                segment_num=seg_num,
                verse_num=seg_num,
                license_he=r["license_he"] or "",
                license_en=r["license_en"],
                version_he=r["version_he"] or "",
                version_en=r["version_en"],
            )
        )

    prev_ref, next_ref = compute_prev_next_unit(clean_ref)

    raw_book_he = rows[0]["author_he"] or rows[0]["book"] or ""
    clean_book_he = re.sub(r"^[•.\s]+", "", raw_book_he).strip()
    clean_book = re.sub(r"^[•.\s]+", "", rows[0]["book"] or "").strip()
    sec_name = format_section_name(clean_ref)

    return ReaderUnitResponse(
        ref=clean_ref,
        book=clean_book,
        book_he=clean_book_he,
        section_name=sec_name,
        author_he=rows[0]["author_he"] or "",
        category_path=rows[0]["category_path"] or "",
        work_id=rows[0]["work_id"] or "",
        segments=segments,
        prev_ref=prev_ref,
        next_ref=next_ref,
    )


# ── Parallels ─────────────────────────────────────────────────────────────────
# The corpus carries commentary→text edges but no parallel edges (Tosefta ↔ Mishnah ↔ Gemara ↔ Midrash), and
# Sefaria's links dataset has no commercial licence we can rely on. So parallels are derived from the texts we
# already hold: passages of the primary literature that share runs of words with this one. Probe the FTS index
# with a few 4-word phrases from the segment, then score each candidate by the 3-word shingles it shares.
_PARALLEL_BASES = {"Mishnah", "Tosefta", "Talmud", "Midrash", "Halakhah"}
_PARALLEL_SKIP_TOP = {"Tanakh", "Reference"}          # a verse quoted in a passage is not a parallel of it
_PARALLEL_MIN_WORDS = 6
_PARALLEL_MIN_SHARED = 3
_PARALLEL_MIN_SCORE = 0.3
_PARALLEL_MAX = 8
_parallels_cache: dict[str, list] = {}


def _shingles(words: list[str], n: int) -> set[str]:
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def _is_commentary_path(path: str) -> bool:
    return any(" on " in part or part == "Commentary" for part in path.split(" / "))


def _parallels(ref: str) -> list[ReaderLinkItem]:
    if ref in _parallels_cache:
        return _parallels_cache[ref]
    out: list[ReaderLinkItem] = []
    db = get_db()
    m = _REF_PARTS.match(ref)
    me = None
    if m:   # chunk_id is '<corpus ref>_<work_id>' and UNIQUE-indexed: a range lookup, not a table scan
        corpus_ref = m.group("title").replace(" ", "_") + "." + m.group("nums").replace(":", ".")
        me = db.execute(
            "SELECT rowid, search_he, book, category_path FROM chunks WHERE chunk_id >= ? AND chunk_id < ? LIMIT 1",
            (corpus_ref + "_", corpus_ref + "`"),
        ).fetchone()
    path = (me["category_path"] if me else "") or ""
    words = ((me["search_he"] if me else "") or "").split()
    if me is None or len(words) < _PARALLEL_MIN_WORDS or path.split(" / ")[0] not in _PARALLEL_BASES             or _is_commentary_path(path):
        _parallels_cache[ref] = out
        return out

    mine = _shingles(words, 3)
    probes = sorted(_shingles(words, 4))
    probes = probes[:: max(1, len(probes) // 10)][:10]
    match = "search_he : (" + " OR ".join('"%s"' % p.replace('"', '""') for p in probes) + ")"
    rows = db.execute(
        """SELECT c.ref, c.book, c.author_he, c.category_path, c.work_id, c.search_he, c.text_he, c.text_en
           FROM search_fts f JOIN chunks c ON c.rowid = f.rowid
           WHERE search_fts MATCH ? AND c.rowid != ? LIMIT 400""",
        (match, me["rowid"]),
    ).fetchall()
    scored = []
    for r in rows:
        cpath = r["category_path"] or ""
        if r["book"] == me["book"] or cpath.split(" / ")[0] in _PARALLEL_SKIP_TOP or _is_commentary_path(cpath):
            continue
        theirs = _shingles((r["search_he"] or "").split(), 3)
        if not theirs:
            continue
        shared = len(mine & theirs)
        score = shared / min(len(mine), len(theirs))
        if shared >= _PARALLEL_MIN_SHARED and score >= _PARALLEL_MIN_SCORE:
            scored.append((score, r))
    scored.sort(key=lambda x: -x[0])
    for _, r in scored[:_PARALLEL_MAX]:
        out.append(ReaderLinkItem(
            ref=r["ref"] or "", source_ref=r["ref"] or "", category=r["category_path"] or r["work_id"] or "parallel",
            type="parallel", author_he=r["author_he"] or r["book"] or "", book=r["book"] or "",
            text_he=r["text_he"], text_en=r["text_en"],
        ))
    if len(_parallels_cache) > 2000:
        _parallels_cache.clear()
    _parallels_cache[ref] = out
    return out


@app.get("/reader/links", response_model=ReaderLinksResponse)
async def reader_links(
    request: Request,
    ref: str = Query(
        ...,
        min_length=1,
        description="Verse/segment reference (e.g. Genesis.1.1, Berakhot.2a.1)",
    ),
):
    # 0. Rate limiting (120 req/min)
    client_key = _get_client_key(request)
    if not _rate_limiter.allow(client_key):
        return JSONResponse(
            status_code=429,
            content={"detail": "rate limit exceeded — please slow down"},
            headers={"Retry-After": "60"},
        )

    clean_ref = ref.strip()
    commentaries: list[ReaderLinkItem] = []
    related: list[ReaderLinkItem] = []

    links_db = get_links_db()
    if links_db is not None:
        canon = canonical_ref(clean_ref)
        canon_keys = [canon]
        for v in with_ref_variants([clean_ref]):
            cv = canonical_ref(v)
            if cv and cv not in canon_keys:
                canon_keys.append(cv)

        placeholders = ",".join("?" for _ in canon_keys)
        edge_rows = links_db.execute(
            f"SELECT to_canon, link_type FROM edges WHERE from_canon IN ({placeholders})",
            canon_keys,
        ).fetchall()

        if edge_rows:
            commentary_items: list[dict] = []
            related_items: list[dict] = []
            seen_to_canon: set[str] = set()

            for row in edge_rows:
                to_canon = str(row["to_canon"] or "").strip()
                link_type = str(row["link_type"] or "").strip().lower()
                if not to_canon or to_canon in seen_to_canon:
                    continue
                seen_to_canon.add(to_canon)

                is_comm = (
                    link_type == "commentary"
                    or " on " in to_canon
                    or any(to_canon.startswith(f"{author} ") for author in KNOWN_AUTHORS_HE)
                )
                item = {"to_canon": to_canon, "link_type": link_type, "is_comm": is_comm}
                if is_comm:
                    commentary_items.append(item)
                else:
                    related_items.append(item)

            all_items = commentary_items + related_items
            item_keys: dict[str, list[str]] = {}
            lookup_keys: list[str] = []
            for item in all_items:
                cand_keys = canon_to_candidate_keys(item["to_canon"])
                item_keys[item["to_canon"]] = cand_keys
                lookup_keys.extend(cand_keys)

            chunks_by_key: dict[str, Any] = {}
            try:
                search_db = get_db()
                unique_keys = list(dict.fromkeys(lookup_keys))
                for i in range(0, len(unique_keys), 200):
                    batch = unique_keys[i : i + 200]
                    batch_placeholders = ",".join("?" for _ in batch)
                    params = batch + batch
                    batch_sql = f"""
                        SELECT chunk_id, ref, book, author_he, category_path, work_id, text_he, text_en
                        FROM chunks
                        WHERE chunk_id IN ({batch_placeholders}) OR ref IN ({batch_placeholders})
                    """
                    found_rows = search_db.execute(batch_sql, params).fetchall()
                    for f in found_rows:
                        if f["chunk_id"]:
                            chunks_by_key[f["chunk_id"]] = f
                            chunks_by_key[canonical_ref(f["chunk_id"])] = f
                        if f["ref"]:
                            chunks_by_key[f["ref"]] = f
                            chunks_by_key[canonical_ref(f["ref"])] = f
            except Exception:
                pass

            def build_reader_link(item: dict) -> ReaderLinkItem:
                to_canon = item["to_canon"]
                cand_keys = item_keys.get(to_canon, [to_canon])
                chunk = None
                for k in cand_keys:
                    if k in chunks_by_key:
                        chunk = chunks_by_key[k]
                        break
                if chunk is None and to_canon in chunks_by_key:
                    chunk = chunks_by_key[to_canon]

                if chunk is not None:
                    return ReaderLinkItem(
                        ref=chunk["ref"] or format_canon_to_ref(to_canon),
                        source_ref=to_canon,
                        category=chunk["category_path"]
                        or chunk["work_id"]
                        or ("commentary" if item["is_comm"] else item["link_type"]),
                        type=item["link_type"],
                        author_he=chunk["author_he"] or format_author_from_canon(to_canon),
                        book=chunk["book"] or format_book_from_canon(to_canon),
                        text_he=chunk["text_he"],
                        text_en=chunk["text_en"],
                    )
                else:
                    return ReaderLinkItem(
                        ref=format_canon_to_ref(to_canon),
                        source_ref=to_canon,
                        category="commentary" if item["is_comm"] else item["link_type"],
                        type=item["link_type"],
                        author_he=format_author_from_canon(to_canon),
                        book=format_book_from_canon(to_canon),
                        text_he=None,
                        text_en=None,
                    )

            commentaries = [build_reader_link(item) for item in commentary_items]
            related = [build_reader_link(item) for item in related_items]

    # Fallback to search_index.db if no links found in links.db
    if not commentaries and not related:
        try:
            search_db = get_db()
            ref_space = clean_ref.replace("_", " ")
            m_comm = re.search(r"on\s+(.*?)[._\s]+(\d+(?:[:.]\d+)?)\b", ref_space, re.IGNORECASE)
            m_base = re.search(r"^([A-Za-z0-9_ ]+)[._\s]+(\d+(?:[:.]\d+)?)\b", ref_space, re.IGNORECASE)

            book_part = None
            cv_part = None
            if m_comm:
                book_part = m_comm.group(1).strip()
                cv_part = m_comm.group(2).strip().replace(".", ":")
            elif m_base:
                book_part = m_base.group(1).strip()
                cv_part = m_base.group(2).strip().replace(".", ":")

            if book_part and book_part.startswith("Tosefta"):
                book_part = None      # the corpus holds no commentary keyed to the Vilna Tosefta's numbering
            if book_part and cv_part:
                # book_part/cv_part come from caller text: escape LIKE
                # metacharacters so only the template's own '%' are wildcards.
                e = like_escape
                p1 = f"%on {e(f'{book_part} {cv_part}:')}%"
                p2 = f"%on {e(f'{book_part}.' + cv_part.replace(':', '.') + '.')}%"
                p3 = f"%on {e(book_part.replace(' ', '_') + '.' + cv_part.replace(':', '.') + '.')}%"
                p4 = f"%on {e(book_part.replace(' ', '_') + '_' + cv_part.replace(':', '_'))}%"
                p5 = f"{book_part} {cv_part}"
                p6 = f"{book_part}.{cv_part.replace(':', '.')}"
                p7 = f"{book_part.replace(' ', '_')}.{cv_part.replace(':', '.')}"

                sql = """
                    SELECT chunk_id, ref, book, author_he, category_path, work_id, text_he, text_en
                    FROM chunks
                    WHERE (ref LIKE ? ESCAPE '\\' OR ref LIKE ? ESCAPE '\\'
                           OR ref LIKE ? ESCAPE '\\' OR ref LIKE ? ESCAPE '\\'
                           OR ref = ? OR ref = ? OR ref = ?)
                      AND ref != ?
                    LIMIT 50
                """
                c_rows = search_db.execute(sql, (p1, p2, p3, p4, p5, p6, p7, clean_ref)).fetchall()
                seen_books: set[str] = set()
                for r in c_rows:
                    if (r["category_path"] or "").startswith("Tosefta"):
                        continue      # Lieberman's Tosefta commentary is numbered differently; never match it to Gemara
                    b_name = r["book"] or r["author_he"] or r["ref"]
                    if b_name in seen_books:
                        continue
                    seen_books.add(b_name)

                    item_type = "commentary" if (" on " in (r["ref"] or "").lower() or " on " in (r["book"] or "").lower()) else "parallel"
                    link_item = ReaderLinkItem(
                        ref=r["ref"] or "",
                        source_ref=r["ref"] or "",
                        category=r["category_path"] or r["work_id"] or item_type,
                        type=item_type,
                        author_he=r["author_he"] or r["book"] or "",
                        book=r["book"] or "",
                        text_he=r["text_he"],
                        text_en=r["text_en"],
                    )
                    if item_type == "commentary":
                        commentaries.append(link_item)
                    else:
                        related.append(link_item)
        except Exception:
            pass

    if not related:
        related = await asyncio.to_thread(_parallels, clean_ref)

    for item in commentaries + related:
        item.ref_he = ref_labels(item.ref)[0]

    return ReaderLinksResponse(
        ref=clean_ref,
        commentaries=commentaries,
        related=related,
        parallels=related,
    )
