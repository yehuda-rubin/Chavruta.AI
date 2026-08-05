"""_is_admin: the admin dashboard's allowlist gate. Mirrors test_calendar_modes.py's coverage of
_calendar_modes_enabled exactly, minus the "*" wildcard case — admin access has no everyone-mode."""

from __future__ import annotations

import app.api as api


def test_admin_disabled_by_default(monkeypatch):
    monkeypatch.delenv("CHAVRUTA_ADMIN_OWNERS", raising=False)
    assert api._is_admin("anyone") is False
    assert api._is_admin("local") is False


def test_admin_enabled_only_for_listed_owners(monkeypatch):
    monkeypatch.setenv("CHAVRUTA_ADMIN_OWNERS", "owner-a, owner-b")
    assert api._is_admin("owner-a") is True
    assert api._is_admin("owner-b") is True
    assert api._is_admin("owner-c") is False


def test_admin_has_no_wildcard(monkeypatch):
    """Unlike CHAVRUTA_CALENDAR_BETA_OWNERS, "*" is not special-cased here — a literal "*" in the
    env var just fails to match any real owner_id, so it's inert rather than meaning "everyone"."""
    monkeypatch.setenv("CHAVRUTA_ADMIN_OWNERS", "*")
    assert api._is_admin("anyone") is False


def test_since_cutoff_windows():
    assert api._since_cutoff("all") is None
    assert api._since_cutoff("garbage") is None
    cutoff_7d = api._since_cutoff("7d")
    cutoff_30d = api._since_cutoff("30d")
    assert cutoff_7d is not None and cutoff_30d is not None
    assert cutoff_7d > cutoff_30d   # 7 days ago is more recent than 30 days ago
