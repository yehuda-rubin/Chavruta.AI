"""The sugya game: the curated content, the unlock rule, and the provenance check.

Two kinds of test here, and the first kind matters more. The CONTENT tests assert that every ref in
every curated file is well-formed and that the levels are internally consistent — because a wrong
ref fails for a reason that has nothing to do with the learner, and would look to them like their
own mistake (docs/CORPUS.md 7: fetch_by_refs is an exact match, a chapter-level ref finds nothing,
and commentary on a daf is three levels deep where commentary on a pasuk is two).

The BEHAVIOUR tests pin the line the module must not cross: it checks provenance, never
understanding, and it never reports a contradiction it could not actually establish.

All offline. No Qdrant, no LLM, no network — the fetcher is injected precisely so this is possible.
"""
from __future__ import annotations

import re

import pytest

from chavruta import sugya

ALL = [s["id"] for s in sugya.available()]

# A ref this corpus can actually match: Sefaria underscore-dot form, at SEGMENT depth. Talmud is
# amud-linear (Bava Metzia 2a -> Bava_Metzia.3.1); commentary on a daf carries an extra level.
REF_RE = re.compile(r"^[A-Za-z][A-Za-z_,'()’-]*(\.\d+){2,3}$")


def test_there_is_content_at_all():
    assert ALL, "no curated sugyot — the feature has nothing to show"


@pytest.mark.parametrize("sugya_id", ALL)
def test_every_curated_file_is_well_formed(sugya_id):
    s = sugya.load(sugya_id)
    assert s.levels, f"{sugya_id} has no levels"
    seen: set[str] = set()
    for lv in s.levels:
        assert lv.id not in seen, f"{sugya_id}: duplicate level id {lv.id}"
        seen.add(lv.id)
        assert lv.goal_he.strip(), f"{sugya_id}/{lv.id}: a level with no goal is not a level"
        assert lv.teach_he.strip(), f"{sugya_id}/{lv.id}: nothing to say once it is solved"
        assert lv.unlocks_ref in lv.accept_refs, (
            f"{sugya_id}/{lv.id}: unlocks {lv.unlocks_ref} but does not accept it — the learner "
            f"could never open the source the level is about")


@pytest.mark.parametrize("sugya_id", ALL)
def test_every_ref_is_shaped_like_a_ref_this_corpus_can_match(sugya_id):
    """Not that the ref EXISTS — that needs the corpus — but that it is not a shape known to match
    nothing. A chapter-level 'Bava_Metzia.3' silently finds zero rows."""
    s = sugya.load(sugya_id)
    for lv in s.levels:
        for ref in lv.accept_refs:
            assert REF_RE.match(ref), f"{sugya_id}/{lv.id}: {ref!r} is not a segment-depth ref"
            assert " " not in ref, f"{sugya_id}/{lv.id}: {ref!r} uses spaces — this corpus uses _"


@pytest.mark.parametrize("sugya_id", ALL)
def test_the_inventory_holds_everything_before_and_nothing_after(sugya_id):
    """The rule the whole design rests on, borrowed from NNG: you may use only what you have already
    unlocked. A level that could lean on a later source would give the next answer away."""
    s = sugya.load(sugya_id)
    for i, lv in enumerate(s.levels):
        inv = s.inventory_at(lv.id)
        assert list(inv) == [x.unlocks_ref for x in s.levels[:i]]
        assert lv.unlocks_ref not in inv, "a level must not start holding its own answer"


# ── The check ────────────────────────────────────────────────────────────────
def _fetch_none(_refs):
    return []


def _fetch_text(text):
    return lambda _refs: [{"text_he": text}]


def test_the_right_source_passes_and_returns_the_teaching():
    s = sugya.load("shnayim-ochazin")
    r = sugya.check(s, "mishnah", "Bava_Metzia.3.1")
    assert r.correct and r.status == "correct"
    assert r.unlocked_ref == "Bava_Metzia.3.1"
    assert r.message_he.strip(), "a correct answer must say what the level was FOR"


def test_a_real_but_wrong_source_is_told_apart_from_one_that_does_not_exist():
    """Two different mistakes deserving two different words: 'you opened the wrong thing' and
    'there is no such thing'. Telling a learner their real citation does not exist would send them
    looking for a typo they did not make."""
    s = sugya.load("shnayim-ochazin")
    real = sugya.check(s, "mishnah", "Bava_Metzia.3.5", fetch=_fetch_text("גמ׳ למה לי למתנא"))
    assert real.status == "wrong_source"
    ghost = sugya.check(s, "mishnah", "Bava_Metzia.999.1", fetch=_fetch_none)
    assert ghost.status == "unknown_ref"


def test_without_a_fetcher_it_never_claims_a_source_does_not_exist():
    """Fail towards the milder statement. With no corpus to ask, 'no such source' is a claim we
    cannot support — the same rule the calendar checker follows with a cold cache."""
    s = sugya.load("shnayim-ochazin")
    assert sugya.check(s, "mishnah", "Bava_Metzia.3.5").status == "wrong_source"


def test_the_right_source_with_words_that_are_not_in_it_is_caught():
    """The real value of the whole exercise: the mistake a person makes when they remember a source
    instead of opening it. No teacher in a class of thirty catches this."""
    s = sugya.load("shnayim-ochazin")
    r = sugya.check(s, "mishnah", "Bava_Metzia.3.1", quote="ולעולם יבנה בידי אדם",
                    fetch=_fetch_text("מתני׳ שנים אוחזין בטלית זה אומר אני מצאתיה"))
    assert not r.correct and r.status == "not_in_source"


def test_a_faithful_quote_passes_despite_punctuation_and_niqqud():
    """Compared on Hebrew letters alone. Otherwise a correct quote fails over a geresh, and the
    learner is told they invented something they copied correctly."""
    s = sugya.load("shnayim-ochazin")
    r = sugya.check(s, "mishnah", "Bava_Metzia.3.1", quote="שנים אוחזין, בטלית!",
                    fetch=_fetch_text("מתני׳ שנים אוחזין בטלית זה אומר אני מצאתיה"))
    assert r.correct, r


def test_an_empty_answer_is_not_a_wrong_answer():
    s = sugya.load("shnayim-ochazin")
    assert sugya.check(s, "mishnah", "  ").status == "no_answer"


def test_a_lookup_failure_is_never_charged_to_the_learner():
    def explode(_refs):
        raise RuntimeError("qdrant is down")

    s = sugya.load("shnayim-ochazin")
    assert sugya.check(s, "mishnah", "Bava_Metzia.3.1", fetch=explode).correct


def test_unknown_ids_raise_rather_than_guess():
    with pytest.raises(sugya.SugyaNotFound):
        sugya.load("no-such-sugya")
    with pytest.raises(sugya.LevelNotFound):
        sugya.check(sugya.load("shnayim-ochazin"), "no-such-level", "Bava_Metzia.3.1")


@pytest.mark.parametrize("evil", ["../../../etc/passwd", "..\\..\\secrets", "a/b"])
def test_a_sugya_id_cannot_escape_the_data_directory(evil):
    """This id arrives in a URL path. Resolving and comparing parents is what actually stops the
    traversal — a substring check on the id would not."""
    with pytest.raises(sugya.SugyaNotFound):
        sugya.load(evil)
