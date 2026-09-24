"""tests/unit/test_search_index.py — Comprehensive tests for SQLite FTS5 search system.

Covers:
  - Building index from sample JSONL chunks
  - Hebrew search (with and without nikud)
  - Reverent divine-name deuphemization (אלוקים -> אלוהים)
  - Language separation (Hebrew vs English)
  - Canonical ordering (Tanakh < Mishnah < Gemara < Shut, alphabetical by sort_title)
  - Facets aggregation and work_id filtering
  - Pagination (offset / limit)
  - Rate limiting (120 req/min)
  - Health check endpoint
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.search_service import (
    SlidingWindowRateLimiter,
    app,
    close_db,
    escape_fts5_query,
    has_hebrew_majority,
)
from scripts.build_search_index import CANONICAL_ORDER, build_index, parse_chunk_record


@pytest.fixture
def sample_chunks() -> list[dict]:
    return [
        {
            "id": "gen_1_1",
            "ref": "Genesis 1:1",
            "book": "Genesis",
            "author_he": "בראשית",
            "work_id": "tanakh",
            "period": "Torah",
            "text_he": "בְּרֵאשִׁית בָּרָא אֱלֹהִים אֵת הַשָּׁמַיִם וְאֵת הָאָרֶץ׃",
            "text_en": "In the beginning God created the heaven and the earth.",
            "license_he": "Public Domain",
            "license_en": "Public Domain",
            "version_he": "Miqra according to the Masorah",
            "version_en": "JPS 1917",
            "category_path": "Tanakh / Torah / Genesis",
        },
        {
            "id": "berakhot_mishnah_1_1",
            "ref": "Mishnah Berakhot 1:1",
            "book": "Mishnah Berakhot",
            "author_he": "ברכות",
            "work_id": "mishnah",
            "period": "Tannaitic",
            "text_he": "מֵאֵימָתַי קוֹרִין אֶת שְׁמַע בְּעַרְבִית",
            "text_en": "From when may one recite the Shema in the evening?",
            "license_he": "Public Domain",
            "license_en": "CC-BY-NC",
            "version_he": "Torat Emet",
            "version_en": "William Davidson Edition",
            "category_path": "Mishnah / Seder Zeraim",
        },
        {
            "id": "bm_2a_1",
            "ref": "Bava Metzia 2a:1",
            "book": "Bava Metzia",
            "author_he": "בבא מציעא",
            "work_id": "gemara",
            "period": "Amoraic",
            "text_he": "שְׁנַיִם אוֹחֲזִין בְּטַלִּית, זֶה אוֹמֵר: אֲנִי מְצָאתִיהָ, וְזֶה אוֹמֵר: אֲנִי מְצָאתִיהָ.",
            "text_en": "Two hold a garment; this one says I found it, and that one says I found it.",
            "license_he": "Public Domain",
            "license_en": "CC-BY-NC",
            "version_he": "Vocalized Bavli",
            "version_en": "William Davidson Edition",
            "category_path": "Talmud / Bavli / Seder Nezikin",
        },
        {
            "id": "bm_2a_2",
            "ref": "Bava Metzia 2a:2",
            "book": "Bava Metzia",
            "author_he": "אבא שאול",
            "work_id": "gemara",
            "period": "Amoraic",
            "text_he": "אמר רב פפא בשם אבא שאול דין חלוקה שווה",
            "text_en": "Rav Pappa said in the name of Abba Shaul: equal division.",
            "license_he": "Public Domain",
            "license_en": "Public Domain",
            "version_he": "Vilna",
            "version_en": "English",
            "category_path": "Talmud / Bavli / Seder Nezikin",
        },
        {
            "id": "igrot_moshe_1",
            "ref": "Igrot Moshe, Orach Chaim 1:1",
            "book": "Igrot Moshe",
            "author_he": "אגרות משה",
            "work_id": "shut",
            "period": "Acharonim",
            "text_he": "בדבר שאלת כבודו בעניין קדושת בית הכנסת ותפילה בציבור",
            "text_en": "",
            "license_he": "CC-BY-SA",
            "license_en": None,
            "version_he": "Responsa Database",
            "version_en": None,
            "category_path": "Responsa / Modern",
        },
        {
            "id": "english_reference_1",
            "ref": "Dictionary of Jewish Terms 1:1",
            "book": "Dictionary of Jewish Terms",
            "author_he": "מילון מונחים",
            "work_id": "reference",
            "period": "Contemporary",
            "text_he": "",
            "text_en": "A comprehensive guide and reference to Jewish halachic terms and customs.",
            "license_he": None,
            "license_en": "CC-BY",
            "version_he": None,
            "version_en": "Reference Edition 2020",
            "category_path": "Reference",
        },
    ]


@pytest.fixture
def search_db(tmp_path: Path, sample_chunks: list[dict]) -> str:
    """Build a search database from sample chunks and configure search_service."""
    jsonl_file = tmp_path / "sample_chunks.jsonl"
    with jsonl_file.open("w", encoding="utf-8") as f:
        for c in sample_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    db_path = tmp_path / "search_index.db"
    build_index(output_path=db_path, jsonl_file=jsonl_file)

    # Point search_service to this test database
    orig_path = os.environ.get("SEARCH_DB_PATH")
    os.environ["SEARCH_DB_PATH"] = str(db_path)
    close_db()

    yield str(db_path)

    close_db()
    if orig_path is not None:
        os.environ["SEARCH_DB_PATH"] = orig_path
    else:
        os.environ.pop("SEARCH_DB_PATH", None)


@pytest.fixture
def client(search_db: str) -> TestClient:
    return TestClient(app)


# ── 1. Index Building & Schema Tests ─────────────────────────────────────────
def test_build_index_creates_tables_and_indices(search_db: str):
    conn = sqlite3.connect(search_db)
    cursor = conn.cursor()

    # Check chunks table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chunks'")
    assert cursor.fetchone() is not None

    # Check search_fts virtual table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='search_fts'")
    assert cursor.fetchone() is not None

    # Check total rows
    cursor.execute("SELECT COUNT(*) FROM chunks")
    count = cursor.fetchone()[0]
    assert count == 6

    # Verify canonical order assigned
    cursor.execute("SELECT work_id, canon_order FROM chunks WHERE chunk_id='gen_1_1'")
    row = cursor.fetchone()
    assert row[0] == "tanakh"
    assert row[1] == CANONICAL_ORDER["tanakh"]

    conn.close()


def test_parse_chunk_record_handles_flat_and_nested_metadata():
    nested = {
        "id": "test_1",
        "document": "some doc",
        "metadata": {
            "ref": "Genesis 1:1",
            "book": "Genesis",
            "work": "tanakh",
            "text_he": "שְׁמַע יִשְׂרָאֵל",
            "text_en": "Hear O Israel",
        },
    }
    rec = parse_chunk_record(nested)
    assert rec["chunk_id"] == "test_1"
    assert rec["ref"] == "Genesis 1:1"
    assert rec["work_id"] == "tanakh"
    assert rec["canon_order"] == 0
    assert "שמע ישראל" in rec["search_he"]
    assert rec["search_en"] == "hear o israel"


# ── 2. Hebrew Search & Nikud Normalization ───────────────────────────────────
def test_hebrew_search_without_nikud_matches_vocalized_text(client: TestClient):
    # Searching plain Hebrew "שנים אוחזין" should match vocalized "שְׁנַיִם אוֹחֲזִין"
    res = client.get("/search/query", params={"q": "שנים אוחזין"})
    assert res.status_code == 200
    data = res.json()
    assert data["lang"] == "he"
    assert data["total"] >= 1
    hit = data["hits"][0]
    assert "Bava Metzia" in hit["ref"]
    assert "<mark>" in hit["snippet"]
    assert "</mark>" in hit["snippet"]


def test_hebrew_search_with_nikud_matches(client: TestClient):
    # User types query with nikud
    res = client.get("/search/query", params={"q": "בְּרֵאשִׁית"})
    assert res.status_code == 200
    data = res.json()
    assert data["lang"] == "he"
    assert data["total"] == 1
    assert data["hits"][0]["ref"] == "Genesis 1:1"


# ── 3. Deuphemization Test (אלוקים -> אלוהים) ──────────────────────────────────
def test_reverent_divine_name_deuphemization(client: TestClient):
    # User queries with reverent 'ק' ("אלוקים")
    # Corpus has true masoretic 'ה' ("אֱלֹהִים")
    res = client.get("/search/query", params={"q": "אלוקים"})
    assert res.status_code == 200
    data = res.json()
    assert data["lang"] == "he"
    assert data["total"] >= 1
    assert any("Genesis 1:1" in hit["ref"] for hit in data["hits"])


# ── 4. Language Separation Tests ─────────────────────────────────────────────
def test_language_separation_hebrew_query_returns_hebrew_only(client: TestClient):
    # Query Hebrew "מדריך" / "בית הכנסת"
    res = client.get("/search/query", params={"q": "בית הכנסת"})
    assert res.status_code == 200
    data = res.json()
    assert data["lang"] == "he"
    assert data["total"] == 1
    assert data["hits"][0]["work_id"] == "shut"
    # Ensure English-only reference chunk is not returned
    assert all(hit["work_id"] != "reference" for hit in data["hits"])


def test_language_separation_english_query_returns_english_only(client: TestClient):
    # Query English "garment"
    res = client.get("/search/query", params={"q": "garment"})
    assert res.status_code == 200
    data = res.json()
    assert data["lang"] == "en"
    assert data["total"] == 1
    hit = data["hits"][0]
    assert hit["ref"] == "Bava Metzia 2a:1"
    assert "<mark>garment</mark>" in hit["snippet"].lower()


def test_language_detection_helper():
    assert has_hebrew_majority("בראשית ברא") is True
    assert has_hebrew_majority("In the beginning") is False
    assert has_hebrew_majority("בראשית in the beginning") is False  # English characters outnumber
    assert has_hebrew_majority("שלום עליכם hello") is True  # Hebrew characters outnumber


# ── 5. Canonical Ordering Tests ──────────────────────────────────────────────
def test_canonical_ordering_across_and_within_tiers(client: TestClient):
    # Search common word "רב" or similar that exists in gemara
    # Or query something in English present in tanakh, mishnah, gemara:
    # "in" appears in Genesis 1:1, Mishnah Berakhot 1:1, and Bava Metzia 2a:2
    res = client.get("/search/query", params={"q": "in", "limit": 10})
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 3

    work_ids = [hit["work_id"] for hit in data["hits"]]
    # Tanakh (0) must appear before Mishnah (1), which must appear before Gemara (3)
    tanakh_idx = work_ids.index("tanakh")
    mishnah_idx = work_ids.index("mishnah")
    gemara_idx = work_ids.index("gemara")

    assert tanakh_idx < mishnah_idx < gemara_idx

    # Within gemara, items should be sorted alphabetically by sort_title (author_he normalized)
    # "אבא שאול" (bm_2a_2) should come before "בבא מציעא" (bm_2a_1)
    gemara_hits = [h for h in data["hits"] if h["work_id"] == "gemara"]
    if len(gemara_hits) >= 2:
        assert gemara_hits[0]["author_he"] == "אבא שאול"
        assert gemara_hits[1]["author_he"] == "בבא מציעא"


# ── 6. Facets Aggregation & Filtering ────────────────────────────────────────
def test_facets_aggregation_and_work_id_filtering(client: TestClient):
    # Query "in" appears in multiple works
    res = client.get("/search/query", params={"q": "in"})
    assert res.status_code == 200
    data = res.json()
    facets = data["facets"]
    assert "tanakh" in facets
    assert "mishnah" in facets
    assert "gemara" in facets
    assert facets["tanakh"] == 1
    assert facets["mishnah"] == 1

    # Filter to only tanakh
    res_filtered = client.get("/search/query", params={"q": "in", "work_id": "tanakh"})
    assert res_filtered.status_code == 200
    data_filtered = res_filtered.json()
    assert data_filtered["total"] == 1
    assert len(data_filtered["hits"]) == 1
    assert data_filtered["hits"][0]["work_id"] == "tanakh"


# ── 7. Pagination Tests ──────────────────────────────────────────────────────
def test_pagination_offset_and_limit(client: TestClient):
    # Query "in" matches at least 3 chunks
    res_page1 = client.get("/search/query", params={"q": "in", "limit": 1, "offset": 0})
    assert res_page1.status_code == 200
    d1 = res_page1.json()
    assert len(d1["hits"]) == 1
    first_ref = d1["hits"][0]["ref"]

    res_page2 = client.get("/search/query", params={"q": "in", "limit": 1, "offset": 1})
    assert res_page2.status_code == 200
    d2 = res_page2.json()
    assert len(d2["hits"]) == 1
    second_ref = d2["hits"][0]["ref"]

    assert first_ref != second_ref
    assert d1["total"] == d2["total"]


# ── 8. Rate Limiting Tests (120 req/min) ──────────────────────────────────────
def test_sliding_window_rate_limiter_unit():
    limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60.0)
    key = "ip:1.2.3.4"
    assert limiter.allow(key) is True
    assert limiter.allow(key) is True
    assert limiter.allow(key) is True
    assert limiter.allow(key) is False  # 4th request exceeds max 3

    # Different key is independent
    assert limiter.allow("ip:5.6.7.8") is True


def test_rate_limit_exceeded_returns_429(client: TestClient):
    from app.search_service import _rate_limiter

    _rate_limiter.reset()
    client_headers = {"X-Forwarded-For": "203.0.113.42"}

    # Simulate 120 successful queries
    for _ in range(120):
        allowed = _rate_limiter.allow("ip:203.0.113.42")
        assert allowed is True

    # 121st request via HTTP client must return 429
    res = client.get("/search/query", params={"q": "שלום"}, headers=client_headers)
    assert res.status_code == 429
    assert res.headers.get("Retry-After") == "60"
    assert "rate limit exceeded" in res.json()["detail"]

    _rate_limiter.reset()


# ── 9. Healthcheck Endpoint ──────────────────────────────────────────────────
def test_health_endpoint(client: TestClient):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["database"] == "ready"


# ── 10. Query Token Escaping ─────────────────────────────────────────────────
def test_escape_fts5_query():
    assert escape_fts5_query('שלום "עולם"') == '"שלום" AND """עולם"""'
    assert escape_fts5_query("  ") == ""


# ── 11. Reader Unit Endpoint (/reader/unit) ──────────────────────────────────
def test_reader_unit_tanakh_chapter(client: TestClient):
    res = client.get("/reader/unit", params={"ref": "Genesis.1"})
    assert res.status_code == 200
    data = res.json()
    assert data["ref"] == "Genesis.1"
    assert data["book"] == "Genesis"
    assert data["work_id"] == "tanakh"
    assert len(data["segments"]) == 1
    seg = data["segments"][0]
    assert seg["ref"] == "Genesis 1:1"
    assert seg["verse_num"] == 1
    assert seg["segment_num"] == 1
    assert "בְּרֵאשִׁית" in seg["text_he"]
    assert "beginning" in seg["text_en"]
    assert seg["license_he"] == "Public Domain"
    assert data["prev_ref"] is None
    assert data["next_ref"] == "Genesis.2"


def test_reader_unit_flexible_ref_matching(client: TestClient):
    # Test space form
    res = client.get("/reader/unit", params={"ref": "Genesis 1"})
    assert res.status_code == 200
    data = res.json()
    assert len(data["segments"]) == 1
    assert data["prev_ref"] is None
    assert data["next_ref"] == "Genesis 2"


def test_reader_unit_talmud_daf(client: TestClient):
    res = client.get("/reader/unit", params={"ref": "Bava Metzia 2a"})
    assert res.status_code == 200
    data = res.json()
    assert data["book"] == "Bava Metzia"
    assert len(data["segments"]) == 2
    assert data["segments"][0]["ref"] == "Bava Metzia 2a:1"
    assert data["segments"][0]["verse_num"] == 1
    assert data["segments"][1]["ref"] == "Bava Metzia 2a:2"
    assert data["segments"][1]["verse_num"] == 2
    assert data["prev_ref"] is None
    assert data["next_ref"] == "Bava Metzia 2b"


def test_reader_unit_not_found(client: TestClient):
    res = client.get("/reader/unit", params={"ref": "Exodus.99"})
    assert res.status_code == 404
    assert "Unit not found" in res.json()["detail"]


# ── 12. Reader Links Endpoint (/reader/links) ─────────────────────────────────
@pytest.fixture
def test_links_db(tmp_path: Path) -> str:
    db_path = tmp_path / "links_corpus.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE edges (from_canon TEXT, to_canon TEXT, link_type TEXT, UNIQUE(from_canon,to_canon))"
    )
    edges = [
        ("genesis 1 1", "rashi on genesis 1 1 1", "commentary"),
        ("genesis 1 1", "ramban on genesis 1 1 1", "commentary"),
        ("genesis 1 1", "bava metzia 2a 1", "reference"),
        ("genesis 1 1", "bereshit rabbah 1 1", "midrash"),
    ]
    conn.executemany("INSERT INTO edges VALUES (?, ?, ?)", edges)
    conn.commit()
    conn.close()

    orig_path = os.environ.get("LINKS_DB_PATH")
    os.environ["LINKS_DB_PATH"] = str(db_path)
    close_db()

    yield str(db_path)

    close_db()
    if orig_path is not None:
        os.environ["LINKS_DB_PATH"] = orig_path
    else:
        os.environ.pop("LINKS_DB_PATH", None)


def test_reader_links_groups_and_populates_text(
    client: TestClient, test_links_db: str, search_db: str
):
    # Also insert Rashi chunk into search_db to verify commentary text fetching
    conn = sqlite3.connect(search_db)
    conn.execute(
        """
        INSERT INTO chunks (
            chunk_id, ref, book, author_he, work_id, period, search_he, search_en,
            text_he, text_en, license_he, license_en, version_he, version_en,
            category_path, canon_order, sort_title
        ) VALUES (
            'rashi_gen_1_1_1', 'Rashi on Genesis 1:1:1', 'Rashi on Genesis', 'רש"י',
            'tanakh', 'Rishonim', 'רשי בראשית', 'rashi in the beginning',
            'בְּרֵאשִׁית בָּרָא אָמַר רַבִּי יִצְחָק', 'Rabbi Yitzchak said...',
            'Public Domain', 'Public Domain', 'Vilna', 'English',
            'Tanakh / Commentary / Rashi', 0, 'רשי על בראשית'
        )
        """
    )
    conn.commit()
    conn.close()
    close_db()

    res = client.get("/reader/links", params={"ref": "Genesis.1.1"})
    assert res.status_code == 200
    data = res.json()
    assert data["ref"] == "Genesis.1.1"

    # Commentaries
    comm = data["commentaries"]
    assert len(comm) == 2
    rashi = next((c for c in comm if "rashi" in c["source_ref"]), None)
    assert rashi is not None
    assert rashi["author_he"] == 'רש"י'
    # Text fetched directly from chunks table
    assert rashi["text_he"] == "בְּרֵאשִׁית בָּרָא אָמַר רַבִּי יִצְחָק"
    assert rashi["text_en"] == "Rabbi Yitzchak said..."

    ramban = next((c for c in comm if "ramban" in c["source_ref"]), None)
    assert ramban is not None
    assert ramban["author_he"] == 'רמב"ן'
    assert ramban["text_he"] is None

    # Related
    rel = data["related"]
    assert len(rel) == 2
    bm = next((r for r in rel if "bava metzia" in r["source_ref"]), None)
    assert bm is not None
    assert bm["book"] == "Bava Metzia"
    # bm_2a_1 was in sample_chunks, so text_he was fetched!
    assert "שְׁנַיִם אוֹחֲזִין" in bm["text_he"]


def test_reader_links_missing_db(client: TestClient):
    orig_path = os.environ.get("LINKS_DB_PATH")
    os.environ["LINKS_DB_PATH"] = "nonexistent_links_db.db"
    close_db()

    try:
        res = client.get("/reader/links", params={"ref": "Genesis.1.1"})
        assert res.status_code == 200
        data = res.json()
        assert data["ref"] == "Genesis.1.1"
        assert isinstance(data["commentaries"], list)
        assert isinstance(data["related"], list)
    finally:
        if orig_path is not None:
            os.environ["LINKS_DB_PATH"] = orig_path
        else:
            os.environ.pop("LINKS_DB_PATH", None)
        close_db()


# ── 13. Availability hardening: LIKE wildcards, FTS5 quoting, rate-limit key ──
@pytest.mark.parametrize("ref", ["_", "%", "%%", "_%", "\\", "_1", "%.1", "Genesis%", "Gen_sis 1"])
def test_reader_unit_like_metacharacters_match_nothing(client: TestClient, ref: str):
    """Caller wildcards must not expand into a whole-table LIKE match."""
    from app.search_service import _rate_limiter

    _rate_limiter.reset()
    res = client.get("/reader/unit", params={"ref": ref})
    assert res.status_code == 404


def test_reader_unit_whitespace_ref_is_404(client: TestClient):
    res = client.get("/reader/unit", params={"ref": "   "})
    assert res.status_code == 404


def test_like_escape_helper():
    from app.search_service import like_escape

    assert like_escape("_") == "\\_"
    assert like_escape("%") == "\\%"
    assert like_escape("a\\b") == "a\\\\b"
    assert like_escape("Bava_Metzia 2a:") == "Bava\\_Metzia 2a:"


def test_reader_unit_row_cap(client: TestClient, monkeypatch):
    import app.search_service as svc

    monkeypatch.setattr(svc, "READER_UNIT_MAX_ROWS", 1)
    res = client.get("/reader/unit", params={"ref": "Bava Metzia 2a"})
    assert res.status_code == 200
    assert len(res.json()["segments"]) == 1


def test_reader_links_fallback_ignores_caller_wildcards(client: TestClient):
    orig_path = os.environ.get("LINKS_DB_PATH")
    os.environ["LINKS_DB_PATH"] = "nonexistent_links_db.db"
    close_db()
    try:
        # "on % 1" would previously match every "... on <anything> 1..." row.
        res = client.get("/reader/links", params={"ref": "Rashi on % 1:1"})
        assert res.status_code == 200
        data = res.json()
        assert data["commentaries"] == [] and data["related"] == []
    finally:
        if orig_path is not None:
            os.environ["LINKS_DB_PATH"] = orig_path
        else:
            os.environ.pop("LINKS_DB_PATH", None)
        close_db()


@pytest.mark.parametrize(
    "token", ['אלוהים"', "אלוהים)", "(אלוהים", 'אלוהים"*', "אלהימ", "ואלהינו"]  # normalized (final letters folded)
)
def test_escape_fts5_hebrew_divine_name_tokens_are_quoted(search_db: str, token: str):
    expr = escape_fts5_query(token, is_he=True)
    assert " OR " in expr  # the divine-name expansion branch was taken
    assert expr.startswith('("') and expr.endswith('")')
    # SQLite must accept it as a valid MATCH expression, alone and combined.
    conn = sqlite3.connect(search_db)
    try:
        for full in (expr, escape_fts5_query(f"בראשית {token} (", is_he=True)):
            conn.execute(
                "SELECT COUNT(*) FROM search_fts WHERE search_fts MATCH ?",
                (f"search_he: ({full})",),
            ).fetchone()
    finally:
        conn.close()


@pytest.mark.parametrize("q", ['אלוהים" OR', "בראשית ברא אלוקים", "אלוהים) OR (", 'ברא "אלהים'])
def test_hebrew_divine_name_queries_do_not_error(client: TestClient, q: str):
    from app.search_service import _rate_limiter

    _rate_limiter.reset()
    res = client.get("/search/query", params={"q": q})
    assert res.status_code == 200


def test_multiword_divine_name_query_finds_verse(client: TestClient):
    from app.search_service import _rate_limiter

    _rate_limiter.reset()
    res = client.get("/search/query", params={"q": "בראשית ברא אלוקים"})
    assert res.status_code == 200
    assert any(h["ref"] == "Genesis 1:1" for h in res.json()["hits"])


def test_search_offset_is_capped(client: TestClient):
    res = client.get("/search/query", params={"q": "in", "offset": 10001})
    assert res.status_code == 422


def test_rate_limit_key_ignores_client_identity_headers(client: TestClient):
    """Rotating X-User-ID / Bearer must not yield a fresh rate-limit bucket."""
    from app.search_service import _rate_limiter

    _rate_limiter.reset()
    for _ in range(120):
        assert _rate_limiter.allow("ip:203.0.113.7") is True
    res = client.get(
        "/search/query",
        params={"q": "in"},
        headers={
            "X-Forwarded-For": "203.0.113.7",
            "X-User-ID": "fresh-id-123",
            "Authorization": "Bearer fresh-token",
        },
    )
    assert res.status_code == 429
    _rate_limiter.reset()

