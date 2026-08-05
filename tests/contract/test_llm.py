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


# bare=True (caught live, 2026-08-05): a one-shot non-QA call (rewrite this sentence; classify
# yes/no) still went through the normal QA template, which wraps `question` in "המקורות (הידע
# היחיד המותר לך)... אם אין תשובה במקורות — אמור זאת ואל תמציא" — and the model sometimes echoed
# that framing back as if it were content. bare skips the template: `question` goes out untouched.
def test_bare_prompt_sends_the_question_verbatim_with_no_qa_wrapping():
    prompt = GroundedPrompt(system="rewrite this", sources=[], question="שה cה הזו", bare=True)
    msgs = render_messages(prompt, "he")
    assert msgs == [
        {"role": "system", "content": "rewrite this"},
        {"role": "user", "content": "שה cה הזו"},
    ]


def test_non_bare_prompt_still_wraps_in_the_qa_template():
    prompt = GroundedPrompt(system="s", sources=[], question="שה cה הזו", bare=False)
    msgs = render_messages(prompt, "he")
    user_content = msgs[-1]["content"]
    assert "אם אין תשובה במקורות" in user_content
    assert "שה cה הזו" in user_content
