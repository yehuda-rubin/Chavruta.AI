"""The improved chavruta path is OFF unless config.rollout.improved_for(True) is active."""
from types import SimpleNamespace

from chavruta.config import rollout
from chavruta.llm import agentic


def test_default_is_off():
    assert rollout.improved() is False
    assert agentic.max_rounds() == agentic.MAX_RETRIEVAL_ROUNDS
    assert agentic.max_queries() == 5


def test_improved_scope_is_restored():
    with rollout.improved_for(True):
        assert rollout.improved() is True
        assert agentic.max_rounds() == agentic.IMPROVED_MAX_RETRIEVAL_ROUNDS
        assert agentic.max_queries() == 2
    assert rollout.improved() is False


def test_parse_need_sources_caps_by_mode():
    text = "===NEED_SOURCES===\na\nb\nc\nd"
    assert len(agentic.parse_need_sources(text)) == 4
    with rollout.improved_for(True):
        assert agentic.parse_need_sources(text) == ["a", "b"]


def test_job_text_differs_by_mode():
    import app.api as api
    hits = [SimpleNamespace(ref="Genesis.1.1", commentator_id=None, text="בראשית ברא")]
    old = api._chavruta_job_md("שאלה", hits, "he", [])
    with rollout.improved_for(True):
        new = api._chavruta_job_md("שאלה", hits, "he", [])
    assert old != new
    assert "{{S" in new and "{{S" not in old


def test_scope_env(monkeypatch):
    monkeypatch.delenv("CHAVRUTA_IMPROVED_SCOPE", raising=False)
    assert rollout.enabled_for(False) is True            # default: everyone
    monkeypatch.setenv("CHAVRUTA_IMPROVED_SCOPE", "admin")
    assert rollout.enabled_for(False) is False and rollout.enabled_for(True) is True
    monkeypatch.setenv("CHAVRUTA_IMPROVED_SCOPE", "off")
    assert rollout.enabled_for(True) is False
