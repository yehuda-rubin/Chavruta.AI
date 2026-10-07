"""The BYO-model headers carry the user's own provider key; no Sentry event may carry them."""
import app.api as api

_SECRET = "sk-user-secret-123"


def _event(headers):
    return {
        "request": {"url": "https://example/api/query", "headers": headers},
        "breadcrumbs": {"values": [
            {"category": "httplib", "data": {"headers": {"X-User-LLM-Key": _SECRET, "Accept": "*/*"}}},
            {"category": "log", "message": "no data here"},
        ]},
    }


def test_scrub_dict_headers():
    ev = api._scrub_sentry_event(_event({
        "X-User-LLM-Key": _SECRET,
        "x-user-llm-base-url": "https://my.provider/v1",
        "X-USER-LLM-MODEL": "my-model",
        "Content-Type": "application/json",
        "User-Agent": "test",
    }), {})
    assert ev["request"]["headers"] == {"Content-Type": "application/json", "User-Agent": "test"}
    assert ev["breadcrumbs"]["values"][0]["data"]["headers"] == {"Accept": "*/*"}
    assert _SECRET not in repr(ev)


def test_scrub_list_headers():
    ev = api._scrub_sentry_event(_event([
        ["x-user-llm-key", _SECRET],
        ("X-User-LLM-Base-URL", "https://my.provider/v1"),
        ["x-user-llm-model", "my-model"],
        ["content-type", "application/json"],
        ["host", "chavrutaai.org"],
    ]), None)
    assert ev["request"]["headers"] == [["content-type", "application/json"], ["host", "chavrutaai.org"]]
    assert _SECRET not in repr(ev)


def test_scrub_tolerates_events_without_request_or_breadcrumbs():
    assert api._scrub_sentry_event({"message": "x"}, None) == {"message": "x"}
    assert api._scrub_sentry_event({"breadcrumbs": [{"data": {"headers": [["X-User-LLM-Key", _SECRET]]}}]},
                                   None)["breadcrumbs"][0]["data"]["headers"] == []
