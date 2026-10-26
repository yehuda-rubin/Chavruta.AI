"""Minor-audience system prompts (spec 009, T040/T041): the safety block, the dropped
modern-cases instruction, and byte-identical adult prompts."""
from __future__ import annotations

import hashlib

import pytest

from chavruta.generation import grounded as g
from chavruta.generation.grounded import (
    MINOR_SAFETY_EN, MINOR_SAFETY_HE, build_lesson_walkthrough_prompt,
    build_prompt,
)
from chavruta.corpus.schema import Intent, LessonPlan, LessonSection

# sha256 of every adult system prompt, captured from the code BEFORE audience_minor existed.
ADULT_SHA256 = {
    "SYSTEM_QA": "0c7ece022599dc3e50ec6ea9f4052aba270e934a0c45d6887a9a4808fbb7f683",
    "SYSTEM_EXPLAIN": "8464efb48f1d52222936496a9886aa06bd97f822833404d5c0c3dfd401cb84e4",
    "SYSTEM_LESSON": "7c5107d917da6463c618c413ce0c6320bd18231de0e83f0edc20bcb7cfdb477f",
    "SYSTEM_BASE_HE": "e0b1a0bcca13c1e8ef622129e51b38a99242f0c54bcb41e3c5b98ce554fc8dfc",
    "SYSTEM_QA_HE": "93abff251737d0218b26523431b60a3884536b62c0ff69962c2dee36394c73eb",
    "SYSTEM_EXPLAIN_HE": "dc9c3802d8b7b5bb43e5042630f9a53adc4339d2e8e9bf52dfc96d8d2fe9372a",
    "SYSTEM_LESSON_HE": "61e8d9075f2252510a775d30737a71b49712537d22f88ef6687198a779698e43",
    "SYSTEM_LESSON_WALKTHROUGH_HE": "907f1306e04f3c46cdc7449c770f96ceb050d8d8069a587c02d9676f4d10a318",
    "SYSTEM_LESSON_WALKTHROUGH": "04a8a329ca87c2211f10ec1ba239de9e9225d18e50dd7f087f994a3cad283320",
    "SYSTEM_SHUT_WALKTHROUGH_HE": "f4db60f44232a1b7df09a3c10d638f9c90e0f01368125bb1363b61ba97980427",
    "SYSTEM_SHUT_WALKTHROUGH": "e1c6106de6563774121054faa844e76d836e30f5178cce614e776be6b4ac9c26",
}

EN_MODERN = "infer the underlying principle FROM the sources"
HE_MODERN = "הסק את העיקרון העולה מן המקורות"
EN_GROUNDING = "You MUST NOT invent sources"
HE_GROUNDING = "אסור להמציא מקורות"


def _plan() -> LessonPlan:
    return LessonPlan(topic="t", sections=[LessonSection(heading="h", citations=[])])


def _all(minor: bool):
    """Every (name, lang, system) the builders can produce, via the real builder paths."""
    out = []
    for lang in ("en", "he"):
        for intent in (Intent.QA, Intent.EXPLAIN, Intent.COMPARE, Intent.LESSON):
            p, _ = build_prompt("q", [], intent=intent, lang=lang, audience_minor=minor)
            out.append((f"build_prompt/{intent.value}", lang, p.system))
        for shut in (False, True):
            p, _ = build_lesson_walkthrough_prompt(_plan(), "q", lang=lang, shut=shut, audience_minor=minor)
            out.append((f"walkthrough/shut={shut}", lang, p.system))
    return out


@pytest.mark.parametrize("name,digest", sorted(ADULT_SHA256.items()))
def test_adult_constants_byte_identical(name, digest):
    assert hashlib.sha256(getattr(g, name).encode()).hexdigest() == digest


def test_adult_builders_return_the_unmodified_constants():
    for lang, qa, ex, les in (("en", g.SYSTEM_QA, g.SYSTEM_EXPLAIN, g.SYSTEM_LESSON),
                              ("he", g.SYSTEM_QA_HE, g.SYSTEM_EXPLAIN_HE, g.SYSTEM_LESSON_HE)):
        assert build_prompt("q", [], intent=Intent.QA, lang=lang)[0].system == qa
        assert build_prompt("q", [], intent=Intent.EXPLAIN, lang=lang)[0].system == ex
        assert build_prompt("q", [], intent=Intent.COMPARE, lang=lang)[0].system == ex
        assert build_prompt("q", [], intent=Intent.LESSON, lang=lang)[0].system == les
    for shut, en, he in ((False, g.SYSTEM_LESSON_WALKTHROUGH, g.SYSTEM_LESSON_WALKTHROUGH_HE),
                         (True, g.SYSTEM_SHUT_WALKTHROUGH, g.SYSTEM_SHUT_WALKTHROUGH_HE)):
        assert build_lesson_walkthrough_prompt(_plan(), "q", lang="en", shut=shut)[0].system == en
        assert build_lesson_walkthrough_prompt(_plan(), "q", lang="he", shut=shut)[0].system == he


def test_adult_prompts_have_no_minor_block_and_keep_modern_cases():
    for _, lang, system in _all(False):
        assert MINOR_SAFETY_HE not in system and MINOR_SAFETY_EN not in system
        assert (HE_MODERN if lang == "he" else EN_MODERN) in system


def test_minor_prompts_every_mode():
    seen = _all(True)
    assert len(seen) == 12
    for name, lang, system in seen:
        block, other = (MINOR_SAFETY_HE, MINOR_SAFETY_EN) if lang == "he" else (MINOR_SAFETY_EN, MINOR_SAFETY_HE)
        assert system.endswith(block), name
        assert other not in system, name
        assert EN_MODERN not in system and HE_MODERN not in system, name
        assert (HE_GROUNDING if lang == "he" else EN_GROUNDING) in system, name
        assert "{{S3:" in system, name  # quote-reference rule survives


def test_minor_prompt_is_adult_prompt_minus_modern_cases_plus_block():
    adult = g._system_for(Intent.QA, "en")
    minor = g._system_for(Intent.QA, "en", True)
    assert minor == adult.replace(g._MODERN_CASES_EN, "") + MINOR_SAFETY_EN


def test_child_safety_placeholder_default_empty_and_appended_when_set(monkeypatch):
    assert g.ANTHROPIC_CHILD_SAFETY_PROMPT == ""
    monkeypatch.setattr(g, "ANTHROPIC_CHILD_SAFETY_PROMPT", "CHILD-SAFETY-TEXT")
    assert build_prompt("q", [], lang="en", audience_minor=True)[0].system.endswith("\n\nCHILD-SAFETY-TEXT")
    assert "CHILD-SAFETY-TEXT" not in build_prompt("q", [], lang="en")[0].system
