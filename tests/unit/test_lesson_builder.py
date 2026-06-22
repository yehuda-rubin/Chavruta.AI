"""Spec 003, Phase 2: arc-structured lesson building from a template."""

from __future__ import annotations

import pytest

from chavruta.config.profile import Profile
from chavruta.corpus.schema import Intent
from chavruta.lessons.builder import build_lesson_from_template, hit_kind
from chavruta.lessons.templates import load_templates
from chavruta.pipeline.pipeline import _top_k_for
from chavruta.retrieval.base import RankedHit


def test_dynamic_top_k_scales_with_intent():
    p = Profile(name="test", top_k=10)
    # a lesson (whole sugya) pulls far more chunks than a short Q&A
    assert _top_k_for(Intent.LESSON, p) > _top_k_for(Intent.EXPLAIN, p) > _top_k_for(Intent.QA, p)
    assert _top_k_for(Intent.LESSON, p) == 48
    assert _top_k_for(Intent.HALACHA, p) == 10   # falls back to profile.top_k


def _tpl(tid):
    return next(t for t in load_templates() if t.template_id == tid)


def _hit(cid, ref, comm=None, work="tanakh", score=1.0):
    return RankedHit(chunk_id=cid, ref=ref, text=f"text of {ref}", score=score,
                     commentator_id=comm, work_id=work)


def test_hit_kind_classification():
    assert hit_kind(_hit("p", "Genesis.1.1")) == "pasuk"
    assert hit_kind(_hit("r", "Rashi on Genesis.1.1", comm="rashi")) == "rishonim"
    assert hit_kind(_hit("m", "Malbim on Genesis.1.1", comm="malbim")) == "acharonim"
    assert hit_kind(_hit("g", "Bava_Metzia.2a", work="talmud_bavli")) == "gemara"


def test_build_arc_opening_branches_convergence():
    hits = [
        _hit("p", "Genesis.1.1", score=1.0),                          # pasuk → opening
        _hit("r", "Rashi on Genesis.1.1", comm="rashi", score=0.9),   # rishon → branch
        _hit("rn", "Ramban on Genesis.1.1", comm="ramban", score=0.8),# rishon → branch
        _hit("m", "Malbim on Genesis.1.1", comm="malbim", score=0.7), # acharon → convergence
    ]
    plan = build_lesson_from_template("המחלוקת בבראשית א:א", _tpl("machloket_rishonim"), hits)

    assert plan.template_id == "machloket_rishonim"
    assert [s.role for s in plan.sections] == ["opening", "branch", "branch", "convergence"]
    assert plan.sections[0].source_refs == ["Genesis.1.1"]                 # opening = anchor
    # two rishonim split across the two branch stages (round-robin)
    assert plan.sections[1].source_refs == ["Rashi on Genesis.1.1"]
    assert plan.sections[2].source_refs == ["Ramban on Genesis.1.1"]
    assert plan.sections[3].source_refs == ["Malbim on Genesis.1.1"]      # convergence
    assert plan.is_open is False
    assert all(s.citations for s in plan.sections)                         # every section grounded


def test_opening_anchors_on_sugya_start():
    """Phase 4: the opening locks onto the anchor (sugya start), not the highest-scored hit."""
    hits = [
        _hit("p2", "Genesis.2.1", score=1.0),                          # higher score, NOT the anchor
        _hit("p1", "Genesis.1.1", score=0.5),                          # the sugya's opening (anchor)
        _hit("r", "Rashi on Genesis.1.1", comm="rashi", score=0.4),
    ]
    plan = build_lesson_from_template("עיון", _tpl("parsha_iyun"), hits, anchor_refs=["Genesis.1.1"])
    assert plan.sections[0].role == "opening"
    assert plan.sections[0].source_refs == ["Genesis.1.1"]             # anchored, not Genesis.2.1


def test_open_sugya_when_no_convergence_source():
    hits = [
        _hit("p", "Genesis.1.1", score=1.0),
        _hit("r", "Rashi on Genesis.1.1", comm="rashi", score=0.9),
    ]
    plan = build_lesson_from_template("עיון פתוח", _tpl("machloket_rishonim"), hits)
    roles = [s.role for s in plan.sections]
    assert "opening" in roles and "branch" in roles
    assert "convergence" not in roles    # no acharonim/pesak source retrieved
    assert plan.is_open is True


# ── Phase 6: every seeded template builds a grounded arc from a mixed source set ──
@pytest.mark.parametrize("tid", [
    "machloket_rishonim", "talmudic_sugya", "parsha_iyun", "machshava_mussar",
])
def test_every_template_builds_grounded_arc(tid):
    hits = [
        _hit("g", "Bava_Metzia.2a", work="talmud_bavli", score=1.0),
        _hit("mi", "Mishnah Bava Metzia.1.1", work="mishnah", score=0.95),
        _hit("p", "Genesis.1.1", score=0.9),
        _hit("r1", "Rashi on X", comm="rashi", score=0.8),
        _hit("r2", "Ramban on X", comm="ramban", score=0.7),
        _hit("a", "Malbim on X", comm="malbim", score=0.6),
    ]
    plan = build_lesson_from_template("נושא", _tpl(tid), hits)
    assert plan.template_id == tid
    assert plan.sections, "arc has at least one section"
    assert all(s.citations for s in plan.sections), "every section is grounded"
    roles = [s.role for s in plan.sections]
    assert roles[0] == "opening", "the arc starts at the source of the sugya"
    assert "branch" in roles, "the arc branches before converging"
