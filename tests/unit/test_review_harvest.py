"""The review/eval-harvest path: the privacy gate, and the mechanical pair harvester.

db.reviewable_questions is the single place the three promises made to users on 2026-08-10 are
enforced (not retroactive, per-chat opt-out, account-wide opt-out). Every one of them is pinned
here, because a privacy condition that is only enforced by a comment is not enforced.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import app.db as db


@pytest.fixture
def fresh_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "review.db")
    monkeypatch.setattr(db, "_conn", None)
    db.get_conn()
    return db


def _session(sid: str, owner: str, created_at: str, *, excluded: int = 0) -> None:
    with db._tx(db.get_conn()) as conn:
        conn.execute(
            "INSERT INTO sessions (id, first_q, created_at, owner_id, excluded_from_review) "
            "VALUES (?,?,?,?,?)", (sid, "q", created_at, owner, excluded))


def _msg(sid: str, text: str, role: str = "user") -> None:
    with db._tx(db.get_conn()) as conn:
        conn.execute(
            "INSERT INTO messages (session_id, role, text, created_at) VALUES (?,?,?,?)",
            (sid, role, text, "2026-08-11T10:00:00"))


AFTER = "2026-08-11T09:00:00"      # safely after the 2026-08-10 effective moment
BEFORE = "2026-08-01T09:00:00"     # collected under the previous promise


# ── Promise 1: NOT retroactive ────────────────────────────────────────────────
def test_conversations_from_before_the_effective_date_are_never_returned(fresh_db):
    """These were collected under 'used only to operate the service'. Out of scope permanently —
    the notice email said so, and users had no chance to object to a use announced afterwards."""
    _session("old", "u1", BEFORE)
    _msg("old", "שאלה ישנה על הלכות שבת")
    assert db.reviewable_questions(opted_out_owners=set()) == []


def test_a_caller_cannot_widen_the_window_by_passing_an_earlier_since(fresh_db):
    """`since` may narrow the window, never widen it past the promise."""
    _session("old", "u1", BEFORE)
    _msg("old", "שאלה ישנה על הלכות שבת")
    assert db.reviewable_questions(since="2020-01-01T00:00:00", opted_out_owners=set()) == []


def test_conversations_after_the_effective_date_are_returned(fresh_db):
    _session("new", "u1", AFTER)
    _msg("new", "האם מותר לשחק במחשב בשבת?")
    got = db.reviewable_questions(opted_out_owners=set())
    assert [r["text"] for r in got] == ["האם מותר לשחק במחשב בשבת?"]


# ── Promise 2: the per-chat opt-out ───────────────────────────────────────────
def test_a_chat_marked_excluded_is_not_returned(fresh_db):
    _session("in", "u1", AFTER)
    _msg("in", "שאלה שנכללת")
    _session("out", "u1", AFTER, excluded=1)
    _msg("out", "שאלה שהוחרגה")
    assert [r["text"] for r in db.reviewable_questions(opted_out_owners=set())] == ["שאלה שנכללת"]


# ── Promise 3: the account-wide opt-out overrides everything ──────────────────
def test_an_account_wide_opt_out_excludes_even_non_excluded_chats(fresh_db):
    _session("s1", "quiet", AFTER)          # chat itself is NOT excluded
    _msg("s1", "שאלה של מי שביקש לצאת")
    _session("s2", "other", AFTER)
    _msg("s2", "שאלה של מישהו אחר")
    got = db.reviewable_questions(opted_out_owners={"quiet"})
    assert [r["text"] for r in got] == ["שאלה של מישהו אחר"]


def test_unknown_opt_out_list_returns_nothing_rather_than_everything(fresh_db):
    """Fail CLOSED. A gate that cannot establish who opted out must take nothing — the alternative
    is reading the conversations of people who asked us not to, on the strength of a lookup that
    happened to fail."""
    _session("s1", "u1", AFTER)
    _msg("s1", "שאלה כלשהי")
    assert db.reviewable_questions(opted_out_owners=None) == []


# ── Only the user's own words, never the assistant's ──────────────────────────
def test_assistant_turns_are_never_returned(fresh_db):
    _session("s1", "u1", AFTER)
    _msg("s1", "שאלת המשתמש")
    _msg("s1", "תשובת המערכת", role="assistant")
    assert [r["text"] for r in db.reviewable_questions(opted_out_owners=set())] == ["שאלת המשתמש"]


# ── The mechanical harvester's labelling ──────────────────────────────────────
# The whole eval set rests on this one derivation being right: if the base ref is wrong, every pair
# is mislabelled and the tuner optimises towards nonsense with no way to notice.
#
# The expected values below were VERIFIED against the live collection, not reasoned out. The first
# version of _base_ref returned the chapter ('Sukkah.81', 'Genesis.1'), and because the scorer
# matches by prefix, every pair would have accepted any segment in the chapter — the eval would have
# reported a retriever far better than the real one, with nothing to reveal it. The probe showed
# Sukkah.81.11 / Genesis.1.1 / Temurah.49.1 exist while Sukkah.81 / Genesis.1 / Temurah.49 do not.
@pytest.mark.parametrize("ref,expected", [
    ("Rashi_on_Sukkah.81.11.2", "Sukkah.81.11"),
    ("Rashi_on_Genesis.1.1.1", "Genesis.1.1"),
    ("Or_HaChaim_on_Genesis.1.25.1", "Genesis.1.25"),
    ("Tosafot_on_Temurah.49.1.1", "Temurah.49.1"),
])
def test_base_ref_is_derived_from_the_commentary_ref(ref, expected):
    from harvest_pairs import _base_ref

    assert _base_ref(ref) == expected


@pytest.mark.parametrize("ref", [
    "Genesis.1.1",                            # a base text has no base to derive
    "Sukkah.81",
    "Mizrachi_on_Rashi_on_Genesis.1.1.1",     # supercommentary: its base is another COMMENTARY,
                                              # so labelling it as base text would be a false label
    "Onkelos_Exodus.20.2",                    # filed as a bare prefix, no _on_ — not a commentary ref
    "Rashi_on_Sukkah.81.11",                  # too few coordinates: dropping the comment index would
                                              # not leave a whole base segment
    "Rashi_on_Berakhot.2a.1.1",               # non-numeric coordinate — a shape never verified
])
def test_base_ref_declines_what_it_cannot_label(ref):
    from harvest_pairs import _base_ref

    assert _base_ref(ref) is None


# ── The daily user-question trickle ───────────────────────────────────────────
@pytest.mark.parametrize("text,useful", [
    ("האם מותר לשחק במחשב בשבת?", True),
    ("תנסה", False),          # conversational glue: as a standalone eval item it has no answer
    ("עוד", False),
    ("כן", False),
    ("תודה", False),
    ("קצר", False),           # under the length floor
    ("א" * 500, False),       # a pasted daf is not a question about one
])
def test_only_self_contained_questions_are_harvested(text, useful):
    from harvest_user_questions import _is_useful

    assert _is_useful(text) is useful
