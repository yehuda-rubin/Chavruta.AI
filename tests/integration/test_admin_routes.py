"""HTTP-level coverage of /admin/* — the same TestClient(api.app) fixture as test_public_stack.py,
proving the real gate: a non-admin owner never sees anything different from a 404 "not found",
and an admin owner reaches real aggregated data."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.api as api
import app.db as db


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db, "_conn", None)
    monkeypatch.setattr(api, "_assert_config_usable", lambda: None)
    fake_pipeline = SimpleNamespace(
        embedding=SimpleNamespace(embed_query=lambda q: SimpleNamespace(dense=[0.0], sparse={})))
    monkeypatch.setattr(api, "_get_pipeline", lambda: fake_pipeline)
    monkeypatch.delenv("CHAVRUTA_ADMIN_OWNERS", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWKS_URL", raising=False)
    with TestClient(api.app) as c:
        yield c


def test_non_admin_gets_404_on_every_admin_route(client, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "k")
    h = {"Authorization": "Bearer k"}
    assert client.get("/admin/overview", headers=h).status_code == 404
    assert client.get("/admin/usage-by-owner", headers=h).status_code == 404
    assert client.get("/admin/usage-by-intent", headers=h).status_code == 404
    assert client.get("/admin/usage-by-week", headers=h).status_code == 404
    assert client.get("/admin/flagged-messages", headers=h).status_code == 404
    assert client.post("/admin/flagged-messages/1/review", headers=h).status_code == 404
    assert client.get("/admin/sessions/some-session-id/messages", headers=h).status_code == 404
    assert client.get("/admin/feedback", headers=h).status_code == 404
    assert client.post("/admin/feedback/1/review", headers=h).status_code == 404
    assert client.get("/admin/coupons", headers=h).status_code == 404
    assert client.post("/admin/coupons", headers=h, json={"kind": "plan"}).status_code == 404
    assert client.delete("/admin/coupons/ABCD", headers=h).status_code == 404
    assert client.post("/admin/grant", headers=h, json={"owner_id": "x"}).status_code == 404


def test_local_unauthenticated_caller_also_gets_404(client):
    assert client.get("/admin/overview").status_code == 404


def test_admin_owner_reaches_overview_with_expected_shape(client, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "k")
    h = {"Authorization": "Bearer k"}
    owner = client.get("/me", headers=h).json()["owner"]

    monkeypatch.setenv("CHAVRUTA_ADMIN_OWNERS", owner)
    r = client.get("/admin/overview", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {"accounts", "usage", "concurrency", "revenue"}
    assert set(body["accounts"].keys()) == {"total", "by_plan"}
    assert set(body["revenue"].keys()) == {"by_plan", "totals"}


def test_me_reflects_is_admin(client, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "k")
    h = {"Authorization": "Bearer k"}
    owner = client.get("/me", headers=h).json()["owner"]
    assert client.get("/me", headers=h).json()["is_admin"] is False

    monkeypatch.setenv("CHAVRUTA_ADMIN_OWNERS", owner)
    assert client.get("/me", headers=h).json()["is_admin"] is True


def test_admin_can_review_a_flagged_message(client, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "k")
    h = {"Authorization": "Bearer k"}
    owner = client.get("/me", headers=h).json()["owner"]
    monkeypatch.setenv("CHAVRUTA_ADMIN_OWNERS", owner)

    # Build the underlying state directly (a session + message + report) rather than driving the
    # real generation pipeline through HTTP — this test is about the /admin routes, not generation.
    sid = db.create_session("x", owner_id=owner)
    msg_id = db.save_message(sid, "assistant", "an answer")
    db.report_message(msg_id, owner, "test")

    unreviewed = client.get("/admin/flagged-messages?reviewed=false", headers=h).json()
    assert len(unreviewed) == 1

    review = client.post(f"/admin/flagged-messages/{unreviewed[0]['id']}/review", headers=h)
    assert review.status_code == 200 and review.json()["ok"] is True

    assert client.get("/admin/flagged-messages?reviewed=false", headers=h).json() == []


# ── Full-chat view for a flagged message (2026-08-19) ─────────────────────────
# A report used to carry only the one flagged line — reading it in the admin panel meant reading a
# claim with no idea what led up to it. This gives a reviewer the whole conversation.
def test_admin_sees_the_full_chat_a_flagged_message_came_from(client, monkeypatch):
    h, admin_owner = _as_admin(client, monkeypatch)

    # The flagged chat belongs to a DIFFERENT, real end user — not the admin's own account. This is
    # the behavior actually being tested: admin_get_session_messages is NOT owner-scoped, unlike
    # the regular GET /sessions/{id}/messages a user hits on their own chats.
    other_owner = "a-real-end-user"
    sid = db.create_session("שרימפס זה כשר", owner_id=other_owner, mode="chavruta")
    db.save_message(sid, "user", "שרימפס זה כשר")
    reply_id = db.save_message(sid, "assistant", "הפסוק 'לא ימיש השרימפ מתוך חלבו' מופיע במשנה...")
    db.report_message(reply_id, other_owner, "user thinks the model invented a source")

    unreviewed = client.get("/admin/flagged-messages?reviewed=false", headers=h).json()
    report = next(r for r in unreviewed if r["message_id"] == reply_id)

    chat = client.get(f"/admin/sessions/{report['session_id']}/messages", headers=h)
    assert chat.status_code == 200, chat.text
    body = chat.json()
    assert [m["role"] for m in body] == ["user", "assistant"]
    assert body[1]["id"] == reply_id
    assert "השרימפ" in body[1]["text"]


def test_admin_full_chat_route_404s_on_an_unknown_session(client, monkeypatch):
    h, _ = _as_admin(client, monkeypatch)
    assert client.get("/admin/sessions/does-not-exist/messages", headers=h).status_code == 404


def test_submit_and_review_feedback(client, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "k")
    h = {"Authorization": "Bearer k"}
    owner = client.get("/me", headers=h).json()["owner"]

    submit = client.post("/feedback/submit", headers=h, json={"text": "יש טעות בשיעור על פרשת נח"})
    assert submit.status_code == 201, submit.text

    monkeypatch.setenv("CHAVRUTA_ADMIN_OWNERS", owner)
    unreviewed = client.get("/admin/feedback?reviewed=false", headers=h).json()
    assert len(unreviewed) == 1
    assert unreviewed[0]["owner_id"] == owner

    review = client.post(f"/admin/feedback/{unreviewed[0]['id']}/review", headers=h)
    assert review.status_code == 200 and review.json()["ok"] is True
    assert client.get("/admin/feedback?reviewed=false", headers=h).json() == []


def test_submit_feedback_rejects_empty_text(client, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "k")
    h = {"Authorization": "Bearer k"}
    assert client.post("/feedback/submit", headers=h, json={"text": "   "}).status_code == 422


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ── Coupons + direct grants (operator) ────────────────────────────────────────
# Issuing used to be CLI-only; these routes put it behind the admin gate so the panel can mint,
# revoke and hand out access. The grant path deliberately goes through a real coupon redemption
# rather than writing the plan directly — see app/api.py::admin_grant.

def _as_admin(client, monkeypatch):
    monkeypatch.setenv("CHAVRUTA_API_KEYS", "k")
    h = {"Authorization": "Bearer k"}
    owner = client.get("/me", headers=h).json()["owner"]
    monkeypatch.setenv("CHAVRUTA_ADMIN_OWNERS", owner)
    return h, owner


def test_admin_creates_lists_and_deletes_an_unused_coupon(client, monkeypatch):
    h, _ = _as_admin(client, monkeypatch)

    created = client.post("/admin/coupons", headers=h,
                          json={"kind": "plan", "plan": "pro", "days": 30, "note": "test"})
    assert created.status_code == 200
    code = created.json()["code"]
    assert code

    listed = client.get("/admin/coupons", headers=h).json()
    assert any(c["note"] == "test" for c in listed)

    # Never redeemed → the row itself goes.
    gone = client.delete(f"/admin/coupons/{code}", headers=h)
    assert gone.status_code == 200 and gone.json()["deleted"] is True
    assert not any(c["note"] == "test" for c in client.get("/admin/coupons", headers=h).json())


def test_admin_delete_keeps_a_redeemed_coupon_and_only_revokes_it(client, monkeypatch):
    h, owner = _as_admin(client, monkeypatch)
    code = client.post("/admin/coupons", headers=h,
                       json={"kind": "credits", "credits": 5, "max_redemptions": 5}).json()["code"]
    # Grant it to somebody so the code carries redemption history.
    assert client.post("/admin/grant", headers=h,
                       json={"owner_id": "someone-else", "kind": "credits",
                             "credits": 5}).status_code == 200
    import app.coupons as coupons
    import app.db as db
    db.redeem_coupon(coupons.normalize(code), "someone-else", "2026-01-01T00:00:00+00:00",
                     "5 credits", set_plan_to=None, period_end=None, add_credits_amount=5)

    res = client.delete(f"/admin/coupons/{code}", headers=h)
    assert res.status_code == 200 and res.json()["deleted"] is False
    row = next(c for c in client.get("/admin/coupons", headers=h).json()
               if c["code"] == coupons.normalize(code))
    assert row["active"] == 0        # revoked, history intact


def test_admin_grants_a_plan_by_owner_id(client, monkeypatch):
    h, _ = _as_admin(client, monkeypatch)
    import app.db as db

    res = client.post("/admin/grant", headers=h,
                      json={"owner_id": "target-user", "kind": "plan", "plan": "pro", "days": 14})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True and body["plan"] == "pro"
    assert db.get_plan("target-user") == "pro"
    # The grant leaves an audit trail: a real coupon, redeemed by that account.
    assert any(r["owner_id"] == "target-user" for r in db.list_redemptions())


def test_admin_grant_credits_by_owner_id(client, monkeypatch):
    h, _ = _as_admin(client, monkeypatch)
    import app.db as db

    before = db.get_credits("credit-target")
    res = client.post("/admin/grant", headers=h,
                      json={"owner_id": "credit-target", "kind": "credits", "credits": 25})
    assert res.status_code == 200
    assert db.get_credits("credit-target") == before + 25


def test_admin_grant_rejects_missing_owner(client, monkeypatch):
    h, _ = _as_admin(client, monkeypatch)
    assert client.post("/admin/grant", headers=h,
                       json={"owner_id": "  ", "kind": "plan"}).status_code == 422


def test_admin_create_coupon_rejects_unknown_plan(client, monkeypatch):
    h, _ = _as_admin(client, monkeypatch)
    res = client.post("/admin/coupons", headers=h, json={"kind": "plan", "plan": "platinum"})
    assert res.status_code == 422


def test_admin_grant_is_not_throttled_across_many_accounts(client, monkeypatch):
    """The redemption throttle guards a public guessing target; an operator handing out access in
    a row would otherwise lock themselves out after ten grants."""
    h, _ = _as_admin(client, monkeypatch)
    for i in range(12):
        res = client.post("/admin/grant", headers=h,
                          json={"owner_id": "bulk-target", "kind": "credits", "credits": 1})
        assert res.status_code == 200, f"grant #{i + 1} failed: {res.text}"
