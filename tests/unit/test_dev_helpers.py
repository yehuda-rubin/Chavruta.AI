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
