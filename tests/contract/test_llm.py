"""Contract: LLMBackend (T023) — answers in the question language; messages carry sources."""

from __future__ import annotations

from chavruta.llm.base import GroundedPrompt, SourceBlock, render_messages


def _prompt():
    return GroundedPrompt(
        system="ground only in sources",
        sources=[SourceBlock(marker="S1", ref="Genesis 1:3", commentator_id="rashi",
                             text="ויאמר אלהים יהי אור")],
        question="What is said about light?",
    )


def test_render_messages_includes_sources_and_marker():
    msgs = render_messages(_prompt(), "en")
    joined = "\n".join(m["content"] for m in msgs)
    assert "[S1]" in joined and "Genesis 1:3" in joined and "rashi" in joined


def test_fake_llm_answers_in_language(fake_llm):
    he = fake_llm.generate(_prompt(), lang="he", max_tokens=64, temperature=0.0)
    en = fake_llm.generate(_prompt(), lang="en", max_tokens=64, temperature=0.0)
    assert "[S1]" in he.text and "[S1]" in en.text
    assert any("֐" <= c <= "׿" for c in he.text)   # Hebrew letters present


def test_no_sources_path(fake_llm):
    empty = GroundedPrompt(system="s", sources=[], question="q")
    out = fake_llm.generate(empty, lang="en", max_tokens=16, temperature=0.0)
    assert "[S" not in out.text
