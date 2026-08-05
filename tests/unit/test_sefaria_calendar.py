"""resolve_parsha / resolve_daf_yomi (src/chavruta/calendar/sefaria_calendar.py).

No live network in tests — `requests.get` is monkeypatched. Covers: a normal response, a combined
("doubled") parsha week, and the retry contract (up to 5 attempts; only ALL failing returns None).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import chavruta.calendar.sefaria_calendar as cal
import pytest
import requests

_NORMAL_RESPONSE = {
    "calendar_items": [
        {"title": {"en": "Parashat Hashavua", "he": "פרשת השבוע"},
         "displayValue": {"en": "Re'eh", "he": "ראה"}, "ref": "Deuteronomy 11:26-16:17"},
        {"title": {"en": "Haftarah", "he": "הפטרה"}, "ref": "Isaiah 54:11-55:5"},
        {"title": {"en": "Daf Yomi", "he": "דף יומי"}, "ref": "Chullin 97"},
    ]
}

_COMBINED_PARSHA_RESPONSE = {
    "calendar_items": [
        {"title": {"en": "Parashat Hashavua", "he": "פרשת השבוע"},
         "displayValue": {"en": "Vayakhel-Pekudei", "he": "ויקהל-פקודי"},
         "ref": "Exodus 35:1-40:38"},
        {"title": {"en": "Daf Yomi", "he": "דף יומי"}, "ref": "Shabbat 45"},
    ]
}


def _resp(json_body, status=200):
    r = MagicMock()
    r.json.return_value = json_body
    r.raise_for_status.side_effect = None if status == 200 else Exception(f"HTTP {status}")
    return r


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr(cal.time, "sleep", lambda *_: None)


def test_resolve_parsha_normal_week(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _resp(_NORMAL_RESPONSE))
    info = cal.resolve_parsha()
    assert info == cal.ParshaInfo(name_en="Re'eh", name_he="ראה", ref_range="Deuteronomy 11:26-16:17",
                                  haftarah_ref="Isaiah 54:11-55:5")


def test_resolve_daf_yomi_normal_day(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _resp(_NORMAL_RESPONSE))
    info = cal.resolve_daf_yomi()
    assert info == cal.DafYomiInfo(tractate="Chullin", daf=97)


def test_resolve_parsha_combined_week(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _resp(_COMBINED_PARSHA_RESPONSE))
    info = cal.resolve_parsha()
    assert info.ref_range == "Exodus 35:1-40:38"
    assert info.name_en == "Vayakhel-Pekudei"


def test_resolve_parsha_missing_haftarah_item_defaults_to_empty(monkeypatch):
    # _COMBINED_PARSHA_RESPONSE has no "Haftarah" entry — must not crash, just default to "".
    monkeypatch.setattr(requests, "get", lambda *a, **k: _resp(_COMBINED_PARSHA_RESPONSE))
    assert cal.resolve_parsha().haftarah_ref == ""


def test_resolve_daf_yomi_combined_week_response(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _resp(_COMBINED_PARSHA_RESPONSE))
    assert cal.resolve_daf_yomi() == cal.DafYomiInfo(tractate="Shabbat", daf=45)


def test_five_failures_in_a_row_returns_none(monkeypatch):
    calls = []

    def _fail(*a, **k):
        calls.append(1)
        raise ConnectionError("network down")

    monkeypatch.setattr(requests, "get", _fail)
    assert cal.resolve_parsha() is None
    assert len(calls) == cal._MAX_ATTEMPTS


def test_four_failures_then_success_on_the_fifth(monkeypatch):
    calls = []

    def _flaky(*a, **k):
        calls.append(1)
        if len(calls) < 5:
            raise ConnectionError("network down")
        return _resp(_NORMAL_RESPONSE)

    monkeypatch.setattr(requests, "get", _flaky)
    info = cal.resolve_parsha()
    assert info is not None
    assert info.ref_range == "Deuteronomy 11:26-16:17"
    assert len(calls) == 5


def test_missing_parsha_item_returns_none(monkeypatch):
    monkeypatch.setattr(requests, "get",
                        lambda *a, **k: _resp({"calendar_items": []}))
    assert cal.resolve_parsha() is None
    assert cal.resolve_daf_yomi() is None
