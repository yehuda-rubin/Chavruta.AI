"""Unit tests for Source Sheet SQLite DB persistence (Spec 008 Phase 1)."""

from __future__ import annotations

import app.db as db


def test_save_and_retrieve_source_sheet(tmp_path, monkeypatch):
    test_db = tmp_path / "test_sourcesheet.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    monkeypatch.setattr(db, "_conn", None)

    sheet_id = "test-sheet-001"
    owner_id = "owner_test_123"
    title = "סוגיית ייאוש שלא מדעת"
    raw_content = "1. בבא מציעא דף כ\"א ע\"א"
    parsed_sheet = [{"index": 1, "header": "בבא מציעא דף כ\"א ע\"א", "ref": "Bava Metzia 21a"}]
    files = [{"name": "sheet.md", "title": "מדריך ליווי", "content": "# חוברת ליווי"}]
    citations = ["Bava Metzia 21a"]

    db.save_source_sheet(
        sheet_id=sheet_id,
        title=title,
        raw_content=raw_content,
        parsed_sheet=parsed_sheet,
        files=files,
        citations=citations,
        owner_id=owner_id,
    )

    # Retrieve by ID
    loaded = db.get_source_sheet(sheet_id, owner_id=owner_id)
    assert loaded is not None
    assert loaded["id"] == sheet_id
    assert loaded["title"] == title
    assert len(loaded["parsed_sheet"]) == 1
    assert loaded["parsed_sheet"][0]["ref"] == "Bava Metzia 21a"
    assert len(loaded["files"]) == 1

    # List sheets
    sheet_list = db.list_source_sheets(owner_id=owner_id)
    assert len(sheet_list) == 1
    assert sheet_list[0]["id"] == sheet_id

    # Delete sheet
    deleted = db.delete_source_sheet(sheet_id, owner_id=owner_id)
    assert deleted is True
    assert db.get_source_sheet(sheet_id, owner_id=owner_id) is None
