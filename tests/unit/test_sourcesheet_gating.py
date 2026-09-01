"""Unit tests for Source Sheet gating and access control (Spec 008 Phase 1)."""

from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

import app.api as api
from chavruta.corpus.schema import Turn


def test_sourcesheet_gating_disabled_by_default(monkeypatch):
    monkeypatch.delenv("CHAVRUTA_SOURCE_SHEET_BETA_OWNERS", raising=False)
    monkeypatch.delenv("CHAVRUTA_ADMIN_OWNERS", raising=False)

    res = api._sourcesheet_mode_enabled("regular_user_123")
    assert res is False

    # Running query as non-beta user returns beta restriction message
    resp = api._run_query_impl(
        question="1. בבא מציעא דף כ\"א ע\"א",
        lang="he",
        intent_str="sourcesheet",
        history=[],
        owner_id="regular_user_123",
    )
    assert "בטא סגורה" in resp.answer
    assert resp.grounded is False


def test_sourcesheet_gating_enabled_for_admin(monkeypatch):
    monkeypatch.setenv("CHAVRUTA_ADMIN_OWNERS", "admin_user_456")

    res = api._sourcesheet_mode_enabled("admin_user_456")
    assert res is True

    resp = api._run_query_impl(
        question="1. בבא מציעא דף כ\"א ע\"א:\nאמר רבא ייאוש שלא מדעת.",
        lang="he",
        intent_str="sourcesheet",
        history=[],
        owner_id="admin_user_456",
    )
    assert resp.grounded is True
    assert len(resp.files) >= 1
    assert "חוברת ליווי" in resp.files[0].title or "Markdown" in resp.files[0].title


def test_sourcesheet_rebuild_request_regex():
    assert api._is_sourcesheet_rebuild_request("תבנה לי דף מקורות חדש") is True
    assert api._is_sourcesheet_rebuild_request("ערוך מחדש את הקובץ") is True
    assert api._is_sourcesheet_rebuild_request("תוציא לי חוברת חדשה") is True
    assert api._is_sourcesheet_rebuild_request("מה רש\"י אמר?") is False
    assert api._is_sourcesheet_rebuild_request("תסביר לי את מקור 2") is False


def test_sourcesheet_followup_continues_conversation(monkeypatch):
    monkeypatch.setenv("CHAVRUTA_ADMIN_OWNERS", "admin_user_456")

    called_chavruta = []

    def fake_chavruta(question, lang, history=None, llm=None):
        called_chavruta.append(question)
        return api.QueryResponse(answer="תשובת חברותא", citations=[], grounded=True, intent="chavruta", files=[])

    monkeypatch.setattr(api, "_run_chavruta", fake_chavruta)

    # History contains an assistant turn from sourcesheet
    history = [
        Turn(role="user", text="1. בבא מציעא דף כ\"א ע\"א"),
        Turn(role="assistant", text="חוברת ליווי", sourcesheet=True),
    ]

    # Asking a conversational follow-up routes to chavruta, not rebuild
    resp = api._run_query_impl(
        question="תסביר לי מה הקושיה של התוספות",
        lang="he",
        intent_str="sourcesheet",
        history=history,
        owner_id="admin_user_456",
    )
    assert len(called_chavruta) == 1
    assert resp.answer == "תשובת חברותא"
