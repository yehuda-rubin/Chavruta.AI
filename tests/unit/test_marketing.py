"""Marketing email: the withdrawal token and who counts as having agreed."""
import pytest

from app import marketing


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "test-secret")


def test_token_round_trips_to_the_user_id():
    uid = "8f1c2d3e-aaaa-bbbb-cccc-1234567890ab"
    assert marketing.verify_token(marketing.make_token(uid)) == uid


def test_altered_token_is_rejected():
    tok = marketing.make_token("user-1")
    body, mac = tok.split(".")
    assert marketing.verify_token(f"{body}.{'0' * len(mac)}") is None
    other = marketing.make_token("user-2").split(".")[0]
    assert marketing.verify_token(f"{other}.{mac}") is None


@pytest.mark.parametrize("bad", ["", "abc", "a.b.c", "....", "!!!.deadbeef"])
def test_malformed_tokens_are_rejected(bad):
    assert marketing.verify_token(bad) is None


def test_no_secret_means_nothing_is_accepted_or_made(monkeypatch):
    tok = marketing.make_token("user-1")
    monkeypatch.delenv("UNSUBSCRIBE_SECRET")
    assert marketing.verify_token(tok) is None
    with pytest.raises(RuntimeError):
        marketing.make_token("user-1")


def test_a_token_signed_under_another_secret_is_rejected(monkeypatch):
    tok = marketing.make_token("user-1")
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "another")
    assert marketing.verify_token(tok) is None


def test_only_an_explicit_true_counts_as_consent():
    assert marketing.has_consent({"user_metadata": {"marketing_consent": True}})
    for meta in ({}, {"marketing_consent": False}, {"marketing_consent": "true"}, {"marketing_consent": None}, {"marketing_consent": 1}):
        assert not marketing.has_consent({"user_metadata": meta})
    assert not marketing.has_consent({})
    assert not marketing.has_consent({"user_metadata": None})


def test_recipients_are_empty_when_supabase_is_not_configured(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    assert marketing.list_marketing_recipients() == []
    assert marketing.withdraw_consent("user-1") is False


def test_unsubscribe_url_points_at_the_proxied_account_prefix():
    url = marketing.unsubscribe_url("user-1")
    assert url.startswith(marketing.SITE_URL + "/account/unsubscribe?t=")
    assert marketing.verify_token(url.split("t=", 1)[1]) == "user-1"


def _script():
    import importlib.util
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "scripts" / "send_product_update.py"
    spec = importlib.util.spec_from_file_location("send_product_update", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_message_is_labelled_advertising_and_carries_one_click_unsubscribe():
    s = _script()
    msg = s.build("a@b.com", "user-1", "שולח: חברותא, contact@example.org", "חברותא <auth@chavrutaai.org>")
    assert msg["Subject"].startswith("פרסומת:")
    assert msg["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    link = msg["List-Unsubscribe"].strip("<>")
    assert marketing.verify_token(link.split("t=", 1)[1]) == "user-1"
    html = msg.get_body(("html",)).get_content()
    assert link in html and "contact@example.org" in html and "{{" not in html
    assert "שדרגנו את המודל" in msg.get_body(("plain",)).get_content()
