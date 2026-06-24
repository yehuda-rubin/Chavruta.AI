"""Responsa (שו"ת) templates — a separate template set for the separate responsa RAG."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from chavruta.lessons.builder import build_lesson_from_template
from chavruta.lessons.templates import SHUT_PATH, TemplateIndex, load_templates
from chavruta.retrieval.base import RankedHit

SEEDED = {"shut_pesak", "shut_tzdadim", "shut_birur_din"}


def test_shut_templates_load_separately_and_well_formed():
    ts = load_templates(SHUT_PATH)
    assert {t.template_id for t in ts} == SEEDED          # its OWN set, not the lesson ones
    lesson_ids = {t.template_id for t in load_templates()}
    assert not (SEEDED & lesson_ids)                       # disjoint from lesson templates
    for t in ts:
        keys = [s.key for s in t.stages]
        assert keys[0] == "opening"
        assert "branch" in keys
        assert t.convergence is not None                   # a teshuva reaches a pesak
        # the opening frames the matter (source/definition), never "restate the question"
        assert "שאל" not in t.opening.title_he


def _hit(cid, ref, comm=None, work="talmud_bavli", score=1.0):
    return RankedHit(chunk_id=cid, ref=ref, text=f"text of {ref}", score=score,
                     commentator_id=comm, work_id=work)


def test_shut_pesak_builds_pesak_arc():
    ts = load_templates(SHUT_PATH)
    pesak = next(t for t in ts if t.template_id == "shut_pesak")
    hits = [
        _hit("g", "Bava Metzia.2a.1", work="talmud_bavli", score=1.0),       # source
        _hit("ri", "Rashba on Bava Metzia.2a.1", comm="rashba", score=0.9),  # rishonim
        _hit("ac", "Mishnah Berurah on X", comm="mishnah_berurah", score=0.8),  # acharonim → pesak
    ]
    plan = build_lesson_from_template("האם מותר…", pesak, hits)
    roles = [s.role for s in plan.sections]
    assert roles[0] == "opening"
    assert "convergence" in roles            # reaches a ruling
    assert plan.is_open is False
    assert all(s.citations for s in plan.sections)


class _KeywordEmbedding:
    KEYS = ["למעשה", "היתר ואיסור", "בירור"]

    def embed_query(self, text):
        return SimpleNamespace(dense=[1.0 if k in text else 0.0 for k in self.KEYS])


def test_shut_selection_picks_within_responsa_set():
    ts = load_templates(SHUT_PATH)
    idx = TemplateIndex(ts, _KeywordEmbedding())
    assert idx.select("שאלה למעשה בהלכות שבת").template_id == "shut_pesak"
    assert idx.select("יש כאן צד היתר ואיסור").template_id == "shut_tzdadim"
    assert idx.select("בירור הגדרת הדין").template_id == "shut_birur_din"
