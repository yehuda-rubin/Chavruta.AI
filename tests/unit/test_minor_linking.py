"""School linking, parents, content settings, safety contacts and alerts (specs/009-school-minors,
T054, T055, T082). Synthetic ids only; no LLM, network or email."""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.api as api
import app.content_settings as content_settings
import app.db as db
import app.minors as minors
import app.orgs as orgs
import app.parents as parents

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "linking.db")
    monkeypatch.setattr(db, "_conn", None)
    monkeypatch.setenv("CHAVRUTA_ADMIN_OWNERS", "ops")
    db.get_conn()
    who = {"v": "boss"}
    api.app.dependency_overrides[api.current_owner] = lambda: who["v"]
    api.app.dependency_overrides[api.require_auth] = lambda: None     # identity is injected above
    client = TestClient(api.app)
    client.who = who
    yield client
    api.app.dependency_overrides.pop(api.current_owner, None)
    api.app.dependency_overrides.pop(api.require_auth, None)


def as_(c, owner):
    c.who["v"] = owner
    return c


def _kid(owner="kid", year=2012, month=5):
    return minors.set_age_once(owner, year, month)


def _adult(owner="mum"):
    return minors.set_age_once(owner, 1980, 1)


def _school():
    oid = orgs.create_org("boss", "בית ספר", "institution")
    return oid


# ── T054: join requests ───────────────────────────────────────────────────────
def test_join_request_flow_and_is_minor_flag(env):
    oid = _school()
    _kid()
    r = as_(env, "boss").post("/orgs/join-requests", json={"owner_id": "kid"})
    assert r.status_code == 201
    rid = r.json()["id"]
    # idempotent while pending
    assert env.post("/orgs/join-requests", json={"owner_id": "kid"}).json()["id"] == rid

    pend = as_(env, "kid").get("/account/join-requests").json()["requests"]
    assert pend == [{"id": rid, "org_name": "בית ספר", "created_at": pend[0]["created_at"]}]
    assert orgs.membership("kid") is None                     # nothing granted before approval

    res = env.post(f"/account/join-requests/{rid}", json={"decision": "approve"})
    assert res.status_code == 200 and res.json()["org_id"] == oid
    m = orgs.membership("kid")
    assert m["role"] == orgs.STUDENT
    row = db.get_conn().execute("SELECT is_minor FROM org_members WHERE owner_id='kid'").fetchone()
    assert row["is_minor"] == 1
    assert env.get("/account/join-requests").json()["requests"] == []
    # a decided request cannot be decided again
    assert env.post(f"/account/join-requests/{rid}", json={"decision": "approve"}).status_code == 404


def test_join_request_404_reveals_nothing(env):
    _school()
    _adult("grown")
    as_(env, "boss")
    for target in ("ghost", "grown", "boss", "local"):
        r = env.post("/orgs/join-requests", json={"owner_id": target})
        assert r.status_code == 404 and r.json() == {"detail": "not found"}
    # a non-admin gets the identical answer
    _kid()
    orgs.accept_invite(orgs.create_invite(orgs.membership("boss")["org_id"], "boss", orgs.TEACHER), "teach")
    assert as_(env, "teach").post("/orgs/join-requests", json={"owner_id": "kid"}).status_code == 404
    assert as_(env, "nobody").post("/orgs/join-requests", json={"owner_id": "kid"}).status_code == 404


def test_decline_and_expiry(env):
    _school()
    _kid()
    rid = as_(env, "boss").post("/orgs/join-requests", json={"owner_id": "kid"}).json()["id"]
    assert as_(env, "kid").post(f"/account/join-requests/{rid}", json={"decision": "decline"}).status_code == 200
    assert orgs.membership("kid") is None
    # a fresh request, then age it past INVITE_DAYS
    rid2 = as_(env, "boss").post("/orgs/join-requests", json={"owner_id": "kid"}).json()["id"]
    old = (datetime.now(UTC) - timedelta(days=orgs.INVITE_DAYS + 1)).isoformat()
    with db._tx(db.get_conn()) as c:
        c.execute("UPDATE org_join_requests SET created_at=? WHERE id=?", (old, rid2))
    assert as_(env, "kid").get("/account/join-requests").json()["requests"] == []
    assert env.post(f"/account/join-requests/{rid2}", json={"decision": "approve"}).status_code == 404
    assert orgs.membership("kid") is None


def test_approval_respects_one_org_and_sticky_removal(env):
    oid = _school()
    _kid()
    other = orgs.create_org("boss2", "אחר", "institution")
    rid = as_(env, "boss").post("/orgs/join-requests", json={"owner_id": "kid"}).json()["id"]
    orgs.accept_invite(orgs.create_invite(other, "boss2", orgs.STUDENT), "kid")   # joins elsewhere meanwhile
    r = as_(env, "kid").post(f"/account/join-requests/{rid}", json={"decision": "approve"})
    assert r.status_code == 409
    assert orgs.membership("kid")["org_id"] == other

    # sticky removal: an admin-removed student cannot be re-requested, nor approve an old request
    _kid("kid2")
    rid2 = as_(env, "boss").post("/orgs/join-requests", json={"owner_id": "kid2"}).json()["id"]
    orgs.accept_invite(orgs.create_invite(oid, "boss", orgs.STUDENT), "kid2")
    orgs.remove_member(oid, "kid2")
    assert as_(env, "kid2").post(f"/account/join-requests/{rid2}", json={"decision": "approve"}).status_code == 409
    assert as_(env, "boss").post("/orgs/join-requests", json={"owner_id": "kid2"}).status_code == 404


def test_accept_invite_marks_minor_but_not_adult(env):
    oid = _school()
    _kid()
    _adult("grown")
    code = orgs.create_invite(oid, "boss", orgs.STUDENT, max_uses=5)
    orgs.accept_invite(code, "kid")
    orgs.accept_invite(code, "grown")
    orgs.accept_invite(code, "legacy")           # no age record at all: stays an adult
    flags = {r["owner_id"]: r["is_minor"] for r in db.get_conn().execute("SELECT owner_id, is_minor FROM org_members")}
    assert flags["kid"] == 1 and flags["grown"] == 0 and flags["legacy"] == 0


def test_school_admin_never_sees_age(env):
    oid = _school()
    _kid()
    orgs.accept_invite(orgs.create_invite(oid, "boss", orgs.STUDENT), "kid")
    panel = as_(env, "boss").get("/orgs/panel")
    assert panel.status_code == 200
    text = panel.text
    for leak in ("birth", "adult_from", "2012"):
        assert leak not in text


# ── T055: parents ─────────────────────────────────────────────────────────────
def test_parent_link_flow(env):
    _kid()
    _adult()
    assert as_(env, "mum").post("/parent/links", json={"child_owner_id": "kid"}).status_code == 201
    # unknown, not-a-minor, self: indistinguishable 404
    for target in ("ghost", "mum"):
        assert env.post("/parent/links", json={"child_owner_id": target}).status_code == 404
    _adult("other-adult")
    assert env.post("/parent/links", json={"child_owner_id": "other-adult"}).status_code == 404
    # pending link grants nothing
    assert env.put("/parent/children/kid/age", json={"birth_year": 2011, "birth_month": 5}).status_code == 404
    assert env.get("/parent/children/kid/content").status_code == 404

    assert as_(env, "kid").get("/account/parent-links").json()["links"][0]["parent_owner_id"] == "mum"
    assert env.post("/account/parent-links/mum", json={"decision": "approve"}).json() == {"status": "active"}

    r = as_(env, "mum").put("/parent/children/kid/age", json={"birth_year": 2011, "birth_month": 5})
    assert r.status_code == 200
    log = db.get_conn().execute(
        "SELECT actor, actor_kind FROM age_record_log WHERE owner_id='kid' ORDER BY id DESC").fetchone()
    assert (log["actor"], log["actor_kind"]) == ("mum", "parent")
    assert env.put("/parent/children/kid/age", json={"birth_year": 2020, "birth_month": 5}).status_code == 422

    # a stranger, and the child, cannot correct the age
    assert as_(env, "stranger").put("/parent/children/kid/age", json={"birth_year": 2000, "birth_month": 1}).status_code == 404
    assert as_(env, "kid").put("/parent/children/kid/age", json={"birth_year": 2000, "birth_month": 1}).status_code == 404

    # revoke by the parent; then the authority is gone
    assert as_(env, "mum").delete("/parent/links/kid").status_code == 204
    assert env.put("/parent/children/kid/age", json={"birth_year": 2011, "birth_month": 5}).status_code == 404
    assert env.delete("/parent/links/kid").status_code == 404


def test_parent_must_be_adult_legacy_or_recorded(env):
    _kid()
    _kid("teen", 2010, 1)
    assert as_(env, "teen").post("/parent/links", json={"child_owner_id": "kid"}).status_code == 403
    # no record and no JWT claim: not an adult either (local/open mode has no claim)
    assert as_(env, "norecord").post("/parent/links", json={"child_owner_id": "kid"}).status_code == 403
    assert parents.is_adult("norecord", legacy_adult=True) is True        # the JWT claim route
    assert parents.request_link("norecord", "kid", legacy_adult=True) is True


def test_child_declines_and_revokes_and_two_parent_cap(env):
    _kid()
    for p in ("a", "b", "c"):
        _adult(p)
        as_(env, p).post("/parent/links", json={"child_owner_id": "kid"})
    as_(env, "kid")
    assert env.post("/account/parent-links/a", json={"decision": "approve"}).status_code == 200
    assert env.post("/account/parent-links/b", json={"decision": "approve"}).status_code == 200
    assert env.post("/account/parent-links/c", json={"decision": "approve"}).status_code == 409
    assert env.post("/account/parent-links/c", json={"decision": "decline"}).status_code == 200
    assert env.delete("/parent/links/kid?parent_id=a").status_code == 204
    assert parents.is_active_parent("a", "kid") is False and parents.is_active_parent("b", "kid") is True
    assert env.delete("/parent/links/kid").status_code == 204
    assert parents.is_active_parent("b", "kid") is False


def test_parent_content_settings_union_with_school(env):
    oid = _school()
    _kid(); _adult()
    orgs.accept_invite(orgs.create_invite(oid, "boss", orgs.STUDENT), "kid")
    as_(env, "mum").post("/parent/links", json={"child_owner_id": "kid"})
    as_(env, "kid").post("/account/parent-links/mum", json={"decision": "approve"})
    assert as_(env, "mum").put("/parent/children/kid/content",
                               json={"disabled": [{"kind": "category", "value": "Chasidut"}]}).status_code == 200
    assert as_(env, "boss").put("/orgs/content",
                                json={"disabled": [{"kind": "work", "value": "Likutei Moharan"}]}).status_code == 200
    rows = set(minors.effective_denylist_rows("kid"))
    assert rows == {("category", "Chasidut"), ("work", "Likutei Moharan")}
    scope = minors.audience_scope("kid")
    assert scope.minor and "Likutei Moharan" in scope.deny.titles
    # revoking the parent link lifts only the parent's rows
    as_(env, "mum").delete("/parent/links/kid")
    assert set(minors.effective_denylist_rows("kid")) == {("work", "Likutei Moharan")}
    # logged
    acts = [r["action"] for r in db.get_conn().execute("SELECT action FROM org_access_log")]
    assert "content:set:1" in acts


# ── content settings ──────────────────────────────────────────────────────────
def test_org_content_tree_validation_and_replace(env):
    oid = _school()
    tree = as_(env, "boss").get("/orgs/content").json()
    assert tree["disabled"] == [] and tree["categories"]
    assert env.put("/orgs/content", json={"disabled": [{"kind": "category", "value": "Chasidut"}]}).status_code == 200
    out = env.get("/orgs/content").json()
    top = {n["id"]: n for n in out["categories"]}
    assert top["Chasidut"]["enabled"] is False
    assert all(not c["enabled"] for c in top["Chasidut"]["children"])          # inherited
    assert all(not b["enabled"] for c in top["Chasidut"]["children"] for b in c["books"])
    # unknown entries refuse the whole call and change nothing
    bad = env.put("/orgs/content", json={"disabled": [{"kind": "work", "value": "Likutei Moharan"},
                                                      {"kind": "work", "value": "No Such Book"},
                                                      {"kind": "category", "value": "Nope/Nope"}]})
    assert bad.status_code == 422
    assert len(bad.json()["detail"]["entries"]) == 2
    assert content_settings.get_disabled("org", oid) == [("category", "Chasidut")]
    # PUT replaces, and a tier slug is accepted
    assert env.put("/orgs/content", json={"disabled": [{"kind": "category", "value": "responsa"}]}).status_code == 422
    assert env.put("/orgs/content", json={"disabled": [{"kind": "category", "value": "shut"}]}).status_code == 200
    assert content_settings.get_disabled("org", oid) == [("category", "shut")]
    assert env.put("/orgs/content", json={"disabled": []}).status_code == 200
    assert content_settings.get_disabled("org", oid) == []
    # non-admin: 404
    orgs.accept_invite(orgs.create_invite(oid, "boss", orgs.TEACHER), "teach")
    assert as_(env, "teach").get("/orgs/content").status_code == 404
    assert env.put("/orgs/content", json={"disabled": []}).status_code == 404
    assert as_(env, "nobody").get("/orgs/content").status_code == 404


# ── safety contacts and alerts ────────────────────────────────────────────────
def _alert(owner, org_id, category="self_harm", danger=0):
    with db._tx(db.get_conn()) as c:
        return c.execute(
            "INSERT INTO crisis_alerts (owner_id, org_id, category, immediate_danger, detector, created_at) "
            "VALUES (?,?,?,?,?,?)", (owner, org_id, category, danger, "phrase", db._now())).lastrowid


def test_safety_contacts_and_alerts(env):
    oid = _school()
    _kid()
    orgs.accept_invite(orgs.create_invite(oid, "boss", orgs.STUDENT), "kid")
    orgs.accept_invite(orgs.create_invite(oid, "boss", orgs.TEACHER), "teach")
    orgs.accept_invite(orgs.create_invite(oid, "boss", orgs.TEACHER), "teach2")
    # members only, and teacher/admin roles only
    assert as_(env, "boss").put("/orgs/safety-contacts", json={"owner_ids": ["stranger"]}).status_code == 422
    assert env.put("/orgs/safety-contacts", json={"owner_ids": ["kid"]}).status_code == 422
    assert env.put("/orgs/safety-contacts", json={"owner_ids": ["teach"]}).json() == {"owner_ids": ["teach"]}
    assert env.get("/orgs/safety-contacts").json() == {"owner_ids": ["teach"]}
    assert as_(env, "teach").put("/orgs/safety-contacts", json={"owner_ids": []}).status_code == 404

    aid = _alert("kid", oid, danger=1)
    other = orgs.create_org("boss2", "אחר", "institution")
    foreign = _alert("x", other)
    unlinked = _alert("lonely", None)

    for who in ("teach", "boss"):
        body = as_(env, who).get("/orgs/alerts").json()["alerts"]
        assert [a["id"] for a in body] == [aid]
        a = body[0]
        assert a == {"id": aid, "student_label": "kid", "category": "self_harm", "immediate_danger": True,
                     "created_at": a["created_at"], "acknowledged": False, "minor": True}
    assert as_(env, "teach2").get("/orgs/alerts").status_code == 404      # teacher but not a contact
    assert as_(env, "kid").get("/orgs/alerts").status_code == 404
    assert as_(env, "nobody").get("/orgs/alerts").status_code == 404

    assert as_(env, "teach2").post(f"/orgs/alerts/{aid}/ack").status_code == 404
    assert as_(env, "teach").post(f"/orgs/alerts/{foreign}/ack").status_code == 404   # another school's
    assert env.post(f"/orgs/alerts/{aid}/ack").status_code == 200
    assert env.get("/orgs/alerts").json()["alerts"][0]["acknowledged"] is True

    # operator: all, including unlinked; non-operator 404
    assert as_(env, "boss").get("/admin/crisis-alerts").status_code == 404
    got = as_(env, "ops").get("/admin/crisis-alerts").json()["alerts"]
    assert {a["id"] for a in got} == {aid, foreign, unlinked}
    assert [a for a in got if a["id"] == unlinked][0]["linked"] is False
    assert env.post(f"/admin/crisis-alerts/{unlinked}/ack").status_code == 200


# ── T082: age authority ───────────────────────────────────────────────────────
def test_operator_age_endpoint(env):
    _kid()
    body = {"birth_year": 2000, "birth_month": 1}
    assert as_(env, "kid").put("/admin/age/kid", json=body).status_code == 404
    assert as_(env, "mum").put("/admin/age/kid", json=body).status_code == 404
    assert as_(env, "ops").put("/admin/age/kid", json=body).status_code == 200
    assert minors.is_minor("kid") is False
    log = db.get_conn().execute("SELECT actor_kind FROM age_record_log ORDER BY id DESC").fetchone()
    assert log["actor_kind"] == "operator"
    assert env.put("/admin/age/ghost", json=body).status_code == 404


def test_parent_correct_requires_active_link_at_function_level(env):
    _kid()
    with pytest.raises(parents.NotLinked):
        parents.correct_child_age("mum", "kid", 2011, 5)
    assert minors.get_age("kid")["birth_year"] == 2012


def test_only_the_verified_wrappers_call_correct_age():
    """T082 guard: a new caller of minors.correct_age must come through parents.py (which checks the
    link) or be added here on purpose."""
    callers = []
    for p in (ROOT / "app").glob("*.py"):
        for line in p.read_text(encoding="utf-8").splitlines():
            if re.search(r"\bcorrect_age\(", line) and not line.lstrip().startswith(("def ", "#", '"""')) \
                    and "`" not in line:
                callers.append(p.name)
    assert set(callers) == {"parents.py"}, callers


def test_new_routes_are_proxied_in_both_configs():
    assert "|parent|" in (ROOT / "docker" / "nginx.conf").read_text(encoding="utf-8")
    assert 'proxy("parent")' in (ROOT / "web" / "next.config.mjs").read_text(encoding="utf-8")
