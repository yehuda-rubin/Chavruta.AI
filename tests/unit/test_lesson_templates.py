"""Spec 003, Phase 1: lesson-template corpus loading + topic-based selection."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from chavruta.lessons.templates import TemplateIndex, load_templates, select_template

SEEDED = {"machloket_rishonim", "talmudic_sugya", "parsha_iyun", "machshava_mussar"}


def test_seed_templates_load_and_are_well_formed():
    ts = load_templates()
    assert SEEDED <= {t.template_id for t in ts}
    for t in ts:
        keys = [s.key for s in t.stages]
        assert keys[0] == "opening"        # every arc starts at the source of the sugya
        assert "branch" in keys            # … and branches before converging
        assert t.opening is not None
        assert len(t.branches) >= 1


# A controllable embedding: one-hot by which template keyword the text contains, so the
# selection is deterministic without a real model.
class _KeywordEmbedding:
    KEYS = ["מחלוקת", "גמרא", "פרשה", "מוסר"]

    def embed_query(self, text: str):
        return SimpleNamespace(dense=[1.0 if k in text else 0.0 for k in self.KEYS])


@pytest.mark.parametrize("topic,expected", [
    ("מהי המחלוקת בין הראשונים בפסוק הזה?", "machloket_rishonim"),
    ("נלמד את סוגיית הגמרא הזו לעומק", "talmudic_sugya"),
    ("עיון בפרשה — מה הרעיון המרכזי?", "parsha_iyun"),
    ("שיעור מוסר על מידת הענווה", "machshava_mussar"),
])
def test_select_template_by_topic(topic, expected):
    ts = load_templates()
    emb = _KeywordEmbedding()
    assert select_template(topic, emb, ts).template_id == expected
    assert TemplateIndex(ts, emb).select(topic).template_id == expected   # cached path agrees
