"""BYOK (bring-your-own-key) quota fallback (app/api.py::_reserve_tokens / _enforce_lesson_quota /
_byok_supported).

The guarantee: once the plan's OWN allowance (db.TOKENS / db.LESSON) is exhausted, a caller-supplied
provider key buys a SECOND allowance of the exact same size, tracked in its own meter
(db.BYOK_TOKENS / db.BYOK_LESSON) — so the two pools never mix, and no key means the old refuse-or-
spend-credits behaviour is completely unchanged.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.api as api
import app.db as db


@pytest.fixture
def fresh_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "byok.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    return db


@pytest.fixture
def api_backend(monkeypatch):
    """A fake pipeline whose profile names an OpenAI-compatible backend — the shape _byok_supported
    checks. 'bridge' is exercised separately."""
    fake = SimpleNamespace(profile=SimpleNamespace(llm_backend="api"))
    monkeypatch.setattr(api, "_get_pipeline", lambda: fake)
    return fake


def test_byok_supported_false_for_bridge_backend(monkeypatch):
    fake = SimpleNamespace(profile=SimpleNamespace(llm_backend="bridge"))
    monkeypatch.setattr(api, "_get_pipeline", lambda: fake)
    assert api._byok_supported() is False


def test_byok_supported_true_for_api_backend(api_backend):
    assert api._byok_supported() is True


def test_byok_supported_false_when_profile_missing(monkeypatch):
    """Defensive: some tests inject a bare fake pipeline with no .profile at all."""
    monkeypatch.setattr(api, "_get_pipeline", lambda: SimpleNamespace())
    assert api._byok_supported() is False


# ── _reserve_tokens (conversation pool) ───────────────────────────────────────
def test_no_key_behaves_exactly_as_before(fresh_db, api_backend, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_FREE", "25000")
    monkeypatch.setenv("CHAVRUTA_TOKENS_WEEK_FREE", "0")
    reserved, used_byok = api._reserve_tokens("u1", "he", "qa")
    assert reserved > 0 and used_byok is False
    assert db.usage_today("u1", meter=db.TOKENS) == reserved


def test_key_unused_while_the_plan_quota_still_has_room(fresh_db, api_backend, monkeypatch):
    """A key is only ever spent as a FALLBACK — never touched while the plan's own pool has room."""
    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_FREE", "25000")
    monkeypatch.setenv("CHAVRUTA_TOKENS_WEEK_FREE", "0")
    reserved, used_byok = api._reserve_tokens("u2", "he", "qa", user_key="sk-user")
    assert used_byok is False
    assert db.usage_today("u2", meter=db.BYOK_TOKENS) == 0


def test_key_admits_a_second_allowance_once_the_plan_quota_is_spent(fresh_db, api_backend, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_FREE", "25000")
    monkeypatch.setenv("CHAVRUTA_TOKENS_WEEK_FREE", "0")
    db.bump_usage("u3", 25_000, units=25_000, meter=db.TOKENS)   # spend the plan's own pool outright

    reserved, used_byok = api._reserve_tokens("u3", "he", "qa", user_key="sk-user")
    assert used_byok is True and reserved > 0
    assert db.usage_today("u3", meter=db.BYOK_TOKENS) == reserved
    assert db.usage_today("u3", meter=db.TOKENS) == 25_000     # the plan's own pool untouched


def test_no_key_still_refuses_once_the_plan_quota_is_spent(fresh_db, api_backend, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_FREE", "25000")
    monkeypatch.setenv("CHAVRUTA_TOKENS_WEEK_FREE", "0")
    monkeypatch.setattr(db, "spend_credits", lambda owner, cost: (False, 0))
    db.bump_usage("u4", 25_000, units=25_000, meter=db.TOKENS)

    with pytest.raises(HTTPException) as exc:
        api._reserve_tokens("u4", "he", "qa")
    assert exc.value.status_code == 429


def test_key_also_refused_once_both_pools_are_spent(fresh_db, api_backend, monkeypatch):
    """A key is not an unlimited escape hatch — it is exactly one more allowance the same size."""
    from fastapi import HTTPException

    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_FREE", "25000")
    monkeypatch.setenv("CHAVRUTA_TOKENS_WEEK_FREE", "0")
    monkeypatch.setattr(db, "spend_credits", lambda owner, cost: (False, 0))
    db.bump_usage("u5", 25_000, units=25_000, meter=db.TOKENS)
    db.bump_usage("u5", 25_000, units=25_000, meter=db.BYOK_TOKENS)

    with pytest.raises(HTTPException) as exc:
        api._reserve_tokens("u5", "he", "qa", user_key="sk-user")
    assert exc.value.status_code == 429


def test_key_ignored_when_backend_does_not_support_byok(fresh_db, monkeypatch):
    """The bridge backend has no provider-key concept — a supplied key must not grant anything."""
    from fastapi import HTTPException

    fake = SimpleNamespace(profile=SimpleNamespace(llm_backend="bridge"))
    monkeypatch.setattr(api, "_get_pipeline", lambda: fake)
    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_FREE", "25000")
    monkeypatch.setenv("CHAVRUTA_TOKENS_WEEK_FREE", "0")
    monkeypatch.setattr(db, "spend_credits", lambda owner, cost: (False, 0))
    db.bump_usage("u6", 25_000, units=25_000, meter=db.TOKENS)

    with pytest.raises(HTTPException):
        api._reserve_tokens("u6", "he", "qa", user_key="sk-user")
    assert db.usage_today("u6", meter=db.BYOK_TOKENS) == 0


# ── _enforce_lesson_quota (its own weekly-count pool) ─────────────────────────
def test_lesson_quota_mirrors_the_same_byok_fallback(fresh_db, api_backend, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_LESSONS_WEEK_FREE", "1")
    db.bump_usage("u7", 0, weekly_limit=1, units=1, meter=db.LESSON)   # spend the week's one lesson

    monkeypatch.setattr(db, "spend_credits", lambda owner, cost: (False, 0))
    used_byok = api._enforce_lesson_quota("u7", "he", user_key="sk-user")
    assert used_byok is True
    assert db.usage_this_week("u7", meter=db.BYOK_LESSON) == 1
    assert db.usage_this_week("u7", meter=db.LESSON) == 1    # unchanged


# ── _resolve_llm_for_request (route-level wiring) ─────────────────────────────
def test_resolve_llm_for_request_builds_a_llm_override_only_on_byok(fresh_db, api_backend, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_FREE", "25000")
    monkeypatch.setenv("CHAVRUTA_TOKENS_WEEK_FREE", "0")
    sentinel = object()
    monkeypatch.setattr(api, "_byok_llm", lambda key, base_url="", model="": sentinel)

    # Plan quota has room: no override, TOKENS meter.
    reserved, llm, meter = api._resolve_llm_for_request("u8", "he", "qa", "sk-user")
    assert llm is None and meter == db.TOKENS

    # Plan quota spent: override present, BYOK_TOKENS meter.
    db.bump_usage("u8", 25_000, units=25_000, meter=db.TOKENS)
    reserved, llm, meter = api._resolve_llm_for_request("u8", "he", "qa", "sk-user")
    assert llm is sentinel and meter == db.BYOK_TOKENS and reserved > 0


def test_resolve_llm_for_request_tolerates_the_fastapi_header_marker(fresh_db, api_backend, monkeypatch):
    """A handful of existing tests call route functions directly, bypassing FastAPI's dependency
    injection — the Header(...) marker object itself lands in user_key rather than a str/None. Must
    not crash, and must behave exactly like "no key supplied"."""
    monkeypatch.setenv("CHAVRUTA_TOKENS_DAY_FREE", "25000")
    monkeypatch.setenv("CHAVRUTA_TOKENS_WEEK_FREE", "0")

    class _NotAString:
        pass

    reserved, llm, meter = api._resolve_llm_for_request("u9", "he", "qa", _NotAString())
    assert llm is None and meter == db.TOKENS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
