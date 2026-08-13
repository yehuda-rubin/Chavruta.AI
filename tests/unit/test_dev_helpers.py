"""Development helpers: consent, the quota floor, feature grants, notices, and deletion.

The tests that matter most here are the ones about CONSENT and about the FLOOR. Being enrolled
changes what an account can do and shows it code nobody has reviewed in front of users, so nothing
may apply before the person agrees. And the allowance is a floor rather than an assignment, because
the alternative — an override — would quietly take allowance away from a helper who also pays.
"""
from __future__ import annotations

import pytest

import app.db as db
import app.devhelpers as devhelpers
import app.orgs as orgs

BOSS = "operator-1"
HELPER = "helper-1"
OTHER = "helper-2"


@pytest.fixture
def fresh_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "helpers.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    return db


# ── Consent ──────────────────────────────────────────────────────────────────
def test_an_invitation_grants_nothing_until_it_is_accepted(fresh_db):
    """The whole reason this is an offer. Before the person says yes there is no quota change and no
    feature — an operator who could enrol silently could hand an unreleased feature to a stranger."""
    devhelpers.invite(HELPER, by=BOSS, features=["sugya"])
    assert devhelpers.get(HELPER)["status"] == "invited"
    assert not devhelpers.is_active(HELPER)
    assert devhelpers.plan_floor(HELPER) is None
    assert not devhelpers.has_feature(HELPER, "sugya")
    assert orgs.effective_plan(HELPER) == "free"

    assert devhelpers.accept(HELPER)
    assert devhelpers.is_active(HELPER)
    assert devhelpers.has_feature(HELPER, "sugya")
    assert orgs.effective_plan(HELPER) == "basic"


def test_accepting_is_idempotent_and_declining_is_recorded(fresh_db):
    devhelpers.invite(HELPER, by=BOSS)
    assert devhelpers.accept(HELPER) and devhelpers.accept(HELPER)
    assert devhelpers.decline(HELPER)
    row = devhelpers.get(HELPER)
    # The row is KEPT, marked declined — the operator should see they were asked and answered,
    # not be left wondering whether the invitation ever arrived.
    assert row["status"] == "declined" and not row["active"]
    assert devhelpers.plan_floor(HELPER) is None


def test_accepting_something_never_offered_does_nothing(fresh_db):
    assert not devhelpers.accept("stranger")
    assert devhelpers.get("stranger") is None


def test_a_revoked_offer_cannot_be_accepted(fresh_db):
    devhelpers.invite(HELPER, by=BOSS)
    devhelpers.revoke(HELPER)
    assert not devhelpers.accept(HELPER)
    assert not devhelpers.is_active(HELPER)


def test_re_inviting_does_not_reset_an_existing_consent(fresh_db):
    """Editing the note or the features of someone already helping must not silently un-accept them
    and leave the operator wondering why their access stopped."""
    devhelpers.invite(HELPER, by=BOSS, features=["sugya"])
    devhelpers.accept(HELPER)
    devhelpers.invite(HELPER, by=BOSS, note="בודק שיעורים", features=[])
    row = devhelpers.get(HELPER)
    assert row["status"] == "accepted" and row["note"] == "בודק שיעורים"
    assert row["features"] == []            # the grant changed…
    assert row["active"]                    # …the consent did not


def test_the_operator_cannot_enrol_themselves(fresh_db):
    with pytest.raises(ValueError):
        devhelpers.invite(BOSS, by=BOSS)


# ── The floor ────────────────────────────────────────────────────────────────
def test_the_allowance_is_a_floor_and_never_takes_away_a_paid_tier(fresh_db):
    """Someone who pays for pro and agrees to help test must not be dropped to basic. Writing this
    as an override instead of a floor is exactly how that would have happened."""
    fresh_db.set_plan(HELPER, "pro")
    devhelpers.invite(HELPER, by=BOSS)
    devhelpers.accept(HELPER)
    assert orgs.effective_plan(HELPER) == "pro"


def test_the_floor_lifts_a_free_account(fresh_db):
    devhelpers.invite(HELPER, by=BOSS)
    devhelpers.accept(HELPER)
    assert orgs.effective_plan(HELPER) == "basic"


# ── Features ─────────────────────────────────────────────────────────────────
def test_an_unknown_feature_id_is_dropped_rather_than_stored(fresh_db):
    """A typo would create a grant matching nothing, which looks exactly like the feature being
    broken — and would be debugged as one."""
    devhelpers.invite(HELPER, by=BOSS, features=["sugya", "sugia", "", "admin"])
    assert devhelpers.get(HELPER)["features"] == ["sugya"]


def test_revoking_takes_the_features_with_it(fresh_db):
    devhelpers.invite(HELPER, by=BOSS, features=["sugya"])
    devhelpers.accept(HELPER)
    devhelpers.revoke(HELPER)
    assert not devhelpers.has_feature(HELPER, "sugya")


# ── Notices ──────────────────────────────────────────────────────────────────
def test_a_notice_fans_out_to_each_recipient_and_only_to_helpers(fresh_db):
    devhelpers.invite(HELPER, by=BOSS)
    devhelpers.invite(OTHER, by=BOSS)
    devhelpers.accept(HELPER)
    # 'stranger' is not on the list: this must never become a way to message users at large.
    sent = devhelpers.send([HELPER, OTHER, "stranger"], "בדקו בבקשה את מצב הסוגיה", by=BOSS)
    assert sent == 2
    assert devhelpers.inbox("stranger") == []
    # Sent to someone still deciding, on purpose — "would you help me test?" belongs next to the offer.
    assert len(devhelpers.inbox(OTHER)) == 1


def test_reading_is_scoped_to_the_owner(fresh_db):
    devhelpers.invite(HELPER, by=BOSS)
    devhelpers.invite(OTHER, by=BOSS)
    devhelpers.send([HELPER], "הודעה", by=BOSS)
    mid = devhelpers.inbox(HELPER)[0]["id"]
    assert not devhelpers.mark_read(OTHER, mid), "an id from a client is not proof of whose it is"
    assert devhelpers.mark_read(HELPER, mid)
    assert not devhelpers.mark_read(HELPER, mid), "already read"
    assert devhelpers.inbox(HELPER, unread_only=True) == []


def test_an_empty_notice_is_refused(fresh_db):
    devhelpers.invite(HELPER, by=BOSS)
    with pytest.raises(ValueError):
        devhelpers.send([HELPER], "   ", by=BOSS)


def test_status_shows_the_person_the_note_written_about_them(fresh_db):
    """No hidden dossier. The operator's label is information held about a person, and they have a
    right to it — cheaper and more honest to just show it than to field the access request."""
    devhelpers.invite(HELPER, by=BOSS, note="בודק שיעורים")
    assert devhelpers.status_for(HELPER)["note"] == "בודק שיעורים"


# ── Deletion ─────────────────────────────────────────────────────────────────
def test_deleting_an_account_takes_its_enrolment_and_notices_with_it(fresh_db):
    """Unlike guard_findings — which carries no owner_id precisely so it needs no handling — both of
    these are ABOUT a person and must go when the account does."""
    devhelpers.invite(HELPER, by=BOSS)
    devhelpers.accept(HELPER)
    devhelpers.send([HELPER], "הודעה", by=BOSS)

    fresh_db.purge_owner(HELPER)

    assert devhelpers.get(HELPER) is None
    assert devhelpers.inbox(HELPER) == []


def test_deleting_the_operator_leaves_the_helpers_but_not_their_name(fresh_db):
    devhelpers.invite(HELPER, by=BOSS)
    devhelpers.send([HELPER], "הודעה", by=BOSS)

    fresh_db.purge_owner(BOSS)

    row = devhelpers.get(HELPER)
    assert row is not None, "the helper's own row is not the operator's to delete"
    assert row["added_by"] == fresh_db.DELETED_OWNER


# ── The admin panel's per-account view ───────────────────────────────────────
def test_top_users_excludes_the_anonymised_rows_of_deleted_accounts(fresh_db):
    """purge_owner NULLs usage_events.owner_id instead of deleting the row, so the measurements stay
    true. A plain GROUP BY then collapses everyone who ever left into one nameless row — which
    ranked fourth in "top users" on the live panel and would only climb. It is not a user."""
    def _event(owner, tokens):
        fresh_db.record_usage_event(
            at="2026-08-13T10:00:00+00:00", hour_local=13, dow=4, owner_id=owner, plan="free",
            intent="qa", lang="he", prompt_tokens=10, completion_tokens=10, billed_tokens=tokens,
            llm_calls=1, ms=1000, concurrent_at_start=1, grounded=1, no_source=0, citations=2,
            audience=None, grade_band=None, length=None, attachments=0, error=None)

    _event(HELPER, 40)
    _event(None, 99999)          # what a purged account's request becomes

    rows = fresh_db.usage_by_owner()
    assert [r["owner_id"] for r in rows] == [HELPER]
    # The anonymised request is still counted where it belongs — only the per-ACCOUNT view drops it.
    assert fresh_db.usage_health()["requests"] == 2


# ── Findings from the pre-deploy review, 2026-08-13 ──────────────────────────
def test_re_inviting_a_revoked_person_asks_again(fresh_db):
    """The door the module's docstring says cannot exist. `invite` cleared revoked_at but left
    accepted_at, so a revoked person went straight back to active — new features and all — without
    ever seeing a prompt, because the invitation panel only renders for status 'invited'."""
    devhelpers.invite(HELPER, by=BOSS)
    devhelpers.accept(HELPER)
    devhelpers.revoke(HELPER)

    devhelpers.invite(HELPER, by=BOSS, features=["sugya"])

    row = devhelpers.get(HELPER)
    assert row["status"] == "invited" and not row["active"]
    assert not devhelpers.has_feature(HELPER, "sugya")
    assert orgs.effective_plan(HELPER) == "free"
    assert devhelpers.accept(HELPER) and devhelpers.has_feature(HELPER, "sugya")


def test_declining_erases_the_note_and_the_messages(fresh_db):
    """A refusal should not leave the operator's description of that person on file, nor a mailbox
    that keeps filling. What survives is the minimum that stops a blind re-invitation."""
    devhelpers.invite(HELPER, by=BOSS, note="בודק שיעורים", features=["sugya"])
    devhelpers.send([HELPER], "הודעה", by=BOSS)

    devhelpers.decline(HELPER)

    row = devhelpers.get(HELPER)
    assert row["status"] == "declined"
    assert row["note"] == "" and row["features"] == []
    assert devhelpers.inbox(HELPER) == []


def test_a_refusal_stops_the_notices(fresh_db):
    """Filtering only on revoked_at let someone who pressed 'no thank you' keep receiving operator
    messages, with a read receipt recorded for each."""
    devhelpers.invite(HELPER, by=BOSS)
    devhelpers.decline(HELPER)
    assert devhelpers.send([HELPER], "עוד הודעה", by=BOSS) == 0
    assert devhelpers.inbox(HELPER) == []


def test_revoking_does_not_lock_the_person_out_of_the_rest_of_the_period(fresh_db):
    """Quota compares an accumulated counter against the CURRENT limit. A helper who spent their
    basic allowance testing and was then revoked had every later request refused until midnight —
    and until Sunday for the weekly cap — with a message telling them to buy a subscription."""
    devhelpers.invite(HELPER, by=BOSS)
    devhelpers.accept(HELPER)
    fresh_db.bump_usage(HELPER, 600_000, weekly_limit=1_575_000, units=600_000,
                        meter=fresh_db.TOKENS)

    devhelpers.revoke(HELPER)

    assert fresh_db.usage_today(HELPER, meter=fresh_db.TOKENS) == 0
    assert fresh_db.usage_this_week(HELPER, meter=fresh_db.TOKENS) == 0
    allowed, _, _ = fresh_db.bump_usage(HELPER, 200_000, weekly_limit=525_000, units=20_000,
                                        meter=fresh_db.TOKENS)
    assert allowed, "revoked, then locked out of the free tier they fell back to"
