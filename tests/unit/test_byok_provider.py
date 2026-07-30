"""BYOK any-provider/any-model support: app/api.py::_byok_llm overrides and the /byok/check
validation endpoint.

Guarantees pinned:
  - _byok_llm defaults to the deployment's own provider/model/floor when the caller names none.
  - A caller-named base_url/model overrides those defaults, and a custom model gets NO output floor
    (the floor is tuned for OUR configured model, not a model the caller picked elsewhere).
  - /byok/check: no key -> 422; unsupported backend -> 400; the named model actually being at the
    provider -> ok; a mismatch -> the provider's real model list, never a guess; a connection failure
    -> a plain explanation, not a crash.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.api as api
import chavruta.llm.cloud as cloud_mod


@pytest.fixture
def api_backend(monkeypatch):
    fake = SimpleNamespace(
        profile=SimpleNamespace(llm_backend="api", llm_base_url="https://default.example/v1",
                                llm_model="default-model", llm_timeout_s=30.0, llm_max_retries=1,
                                llm_min_output_tokens=8_000),
        wire_source_fetcher=lambda llm: None,
    )
    monkeypatch.setattr(api, "_get_pipeline", lambda: fake)
    return fake


# ── _byok_llm ──────────────────────────────────────────────────────────────────
def test_byok_llm_defaults_to_the_deployments_own_provider(api_backend):
    llm = api._byok_llm("sk-user")
    assert llm.base_url == "https://default.example/v1"
    assert llm.model_id == "default-model"
    assert llm.min_output_tokens == 8_000     # the deployment's own tuned floor applies


def test_byok_llm_custom_base_url_and_model_override_defaults(api_backend):
    llm = api._byok_llm("sk-user", base_url="https://other.example/v1", model="some-other-model")
    assert llm.base_url == "https://other.example/v1"
    assert llm.model_id == "some-other-model"


def test_byok_llm_custom_model_gets_no_output_floor(api_backend):
    """The floor is a property of the model THIS deployment was tuned for — applying it to a model
    the caller picked elsewhere could be wrong either way, so it is not guessed."""
    llm = api._byok_llm("sk-user", model="some-other-model")
    assert llm.min_output_tokens == 0


def test_byok_llm_custom_base_url_alone_keeps_the_default_model_and_floor(api_backend):
    """Only the base URL was overridden — still asking for OUR model at a different host is a real
    use case (e.g. a self-hosted mirror), so the floor still applies."""
    llm = api._byok_llm("sk-user", base_url="https://mirror.example/v1")
    assert llm.model_id == "default-model"
    assert llm.min_output_tokens == 8_000


# ── /byok/check ─────────────────────────────────────────────────────────────────
def test_byok_check_requires_a_key(api_backend):
    with pytest.raises(HTTPException) as exc:
        api.byok_check(api.ByokCheckRequest(model="m"), "he", "u1", None)
    assert exc.value.status_code == 422


def test_byok_check_rejects_unsupported_backend(monkeypatch):
    fake = SimpleNamespace(profile=SimpleNamespace(llm_backend="bridge"))
    monkeypatch.setattr(api, "_get_pipeline", lambda: fake)
    with pytest.raises(HTTPException) as exc:
        api.byok_check(api.ByokCheckRequest(model="m"), "he", "u2", "sk-user")
    assert exc.value.status_code == 400


def test_byok_check_ok_when_model_is_at_the_provider(api_backend, monkeypatch):
    monkeypatch.setattr(cloud_mod, "list_models", lambda base_url, key, timeout_s=15.0: ["a", "b", "m"])
    out = api.byok_check(api.ByokCheckRequest(model="m"), "he", "u3", "sk-user")
    assert out.ok is True and out.models == []


def test_byok_check_returns_the_real_model_list_on_mismatch(api_backend, monkeypatch):
    monkeypatch.setattr(cloud_mod, "list_models",
                        lambda base_url, key, timeout_s=15.0: ["model-a", "model-b"])
    out = api.byok_check(api.ByokCheckRequest(model="does-not-exist"), "he", "u4", "sk-user")
    assert out.ok is False
    assert out.models == ["model-a", "model-b"]
    assert out.message   # a real explanation, not empty


def test_byok_check_reports_connection_failure_without_crashing(api_backend, monkeypatch):
    def boom(base_url, key, timeout_s=15.0):
        raise RuntimeError("bad key")
    monkeypatch.setattr(cloud_mod, "list_models", boom)
    out = api.byok_check(api.ByokCheckRequest(model="m"), "he", "u5", "sk-user")
    assert out.ok is False and out.models == [] and out.message


def test_byok_check_uses_the_supplied_base_url_not_the_default(api_backend, monkeypatch):
    seen = {}

    def spy(base_url, key, timeout_s=15.0):
        seen["base_url"] = base_url
        return ["m"]
    monkeypatch.setattr(cloud_mod, "list_models", spy)
    api.byok_check(api.ByokCheckRequest(model="m", base_url="https://custom.example/v1"),
                   "he", "u6", "sk-user")
    assert seen["base_url"] == "https://custom.example/v1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
