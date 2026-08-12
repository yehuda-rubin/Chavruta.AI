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


# ── The scorer must not credit (or be crowded out by) the query retrieving itself ─────────────
# A harvested query is the verbatim text of a chunk in the collection, so it retrieves itself every
# time — measured 25/25 on the first live sample. That hit proves only that identical text embeds
# identically, and it occupies a top-k slot the real answer needed.
def test_scoring_ignores_the_chunk_the_query_was_taken_from():
    from types import SimpleNamespace

    from tune_retrieval import score

    item = {"question": "טקסט הפירוש", "expected_refs": ["Sukkah.81.11"],
            "source_ref": "Rashi_on_Sukkah.81.11.2"}

    class _Retriever:
        def __init__(self, refs):
            self.refs = refs

        def retrieve(self, query, top_k):
            return SimpleNamespace(hits=[SimpleNamespace(ref=r) for r in self.refs])

    # Self-hit first, real answer second: the self-hit must not push the answer to rank 2.
    got = score(_Retriever(["Rashi_on_Sukkah.81.11.2", "Sukkah.81.11"]), [item], top_k=8)
    assert got["recall"] == 1.0 and got["mrr"] == 1.0

    # Self-hit alone is not a hit at all.
    missed = score(_Retriever(["Rashi_on_Sukkah.81.11.2"]), [item], top_k=8)
    assert missed["recall"] == 0.0 and missed["mrr"] == 0.0


def test_scoring_is_unaffected_for_items_with_no_source_chunk():
    """Human-written questions carry no source_ref — they must score exactly as before."""
    from types import SimpleNamespace

    from tune_retrieval import score

    item = {"question": "האם מותר לשחק בשבת?", "expected_refs": ["Shabbat.1.1"]}

    class _Retriever:
        def retrieve(self, query, top_k):
            return SimpleNamespace(hits=[SimpleNamespace(ref="Shabbat.1.1")])

    assert score(_Retriever(), [item], top_k=8)["recall"] == 1.0


# ── The nightly window ────────────────────────────────────────────────────────
# Requested schedule (Israel local time): every night 00:00-05:00 on 2 CPUs, Saturday 00:00-16:00 on
# 6 CPUs. The window is computed from Asia/Jerusalem rather than a UTC offset because the server runs
# on UTC and Israel moves between UTC+2 and UTC+3 — a hardcoded offset would slide by an hour twice a
# year and start a heavy batch job in the evening, while users are awake.
from datetime import datetime  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

_IL = ZoneInfo("Asia/Jerusalem")


def _at(y, m, d, hour):
    from nightly_eval import window_for

    return window_for(datetime(y, m, d, hour, tzinfo=_IL))


@pytest.mark.parametrize("hour,cpus", [(0, 2), (3, 2), (4, 2)])
def test_weeknight_window_runs_on_two_cpus(hour, cpus):
    got = _at(2026, 8, 12, hour)          # a Wednesday
    assert got is not None and got[1] == cpus


@pytest.mark.parametrize("hour", [5, 6, 12, 18, 23])
def test_outside_the_weeknight_window_nothing_runs(hour):
    """05:00 is the END of the window and must already be outside it — a job admitted at 04:59 is
    bounded by the deadline, but one admitted at 05:00 would run into the morning."""
    assert _at(2026, 8, 12, hour) is None


@pytest.mark.parametrize("hour", [0, 5, 9, 15])
def test_saturday_runs_until_16_00_on_six_cpus(hour):
    got = _at(2026, 8, 15, hour)          # a Saturday
    assert got is not None and got[1] == 6


def test_saturday_takes_precedence_where_the_windows_overlap():
    """Saturday 02:00 is inside both windows; the Saturday budget (6) must win over the nightly (2)."""
    assert _at(2026, 8, 15, 2)[1] == 6


@pytest.mark.parametrize("hour", [16, 17, 23])
def test_saturday_stops_at_16_00(hour):
    assert _at(2026, 8, 15, hour) is None


def test_the_window_end_is_the_deadline_the_run_is_bounded_by():
    from nightly_eval import window_for

    ends, _ = window_for(datetime(2026, 8, 12, 3, 30, tzinfo=_IL))
    assert (ends.hour, ends.minute, ends.day) == (5, 0, 12)

    ends_sat, _ = window_for(datetime(2026, 8, 15, 3, 30, tzinfo=_IL))
    assert (ends_sat.hour, ends_sat.day) == (16, 15)


def test_the_window_follows_israel_dst_not_a_fixed_utc_offset():
    """The same UTC instant falls in the window in winter and outside it in summer. Reading Israel
    local time is what makes that come out right without a twice-yearly cron edit."""
    from datetime import timezone

    from nightly_eval import window_for

    # 03:30 UTC → 06:30 IDT (summer, outside) but 05:30 IST (winter, also outside); the informative
    # pair is 02:30 UTC → 05:30 IDT (outside) vs 04:30 IST (inside).
    summer = datetime(2026, 8, 12, 2, 30, tzinfo=timezone.utc).astimezone(_IL)
    winter = datetime(2026, 1, 14, 2, 30, tzinfo=timezone.utc).astimezone(_IL)
    assert window_for(summer) is None          # 05:30 local — past the window
    assert window_for(winter) is not None      # 04:30 local — still inside it
