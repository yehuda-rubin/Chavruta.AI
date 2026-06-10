"""LLMBackend interface (contracts/llm-backend.md).

Generates the answer from an already-built, source-grounded prompt. The dual-model strategy
lives here: LocalLLM (DictaLM via Ollama) and CloudLLM (Nebius) implement the same interface,
chosen by config. Grounding is enforced by the pipeline, not trusted to the model alone.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class SourceBlock:
    """One retrieved source the model is allowed to use, with a stable marker for citation."""

    marker: str          # e.g. "S1" — the model cites by marker; pipeline maps marker → Citation
    ref: str
    commentator_id: str | None
    text: str


@dataclass
class Turn:
    role: str
    text: str


@dataclass
class GroundedPrompt:
    system: str
    sources: list[SourceBlock]
    question: str
    history: list[Turn] = field(default_factory=list)


@dataclass
class LLMResult:
    text: str
    finish_reason: str = "stop"


def render_messages(prompt: GroundedPrompt, lang: str) -> list[dict]:
    """Render a GroundedPrompt into OpenAI/Ollama chat messages.

    The system message carries the grounding rules. The sources are presented as the ONLY
    knowledge the model may use, each tagged with its marker so the model cites by marker.
    """
    messages: list[dict] = [{"role": "system", "content": prompt.system}]
    for turn in prompt.history:
        messages.append({"role": turn.role, "content": turn.text})

    if prompt.sources:
        lines = []
        for s in prompt.sources:
            who = f" ({s.commentator_id})" if s.commentator_id else ""
            lines.append(f"[{s.marker}] {s.ref}{who}:\n{s.text}")
        sources_block = "\n\n".join(lines)
    else:
        sources_block = "(no sources retrieved)"

    answer_lang = "Hebrew" if lang == "he" else "English"
    user = (
        f"SOURCES (the only knowledge you may use):\n{sources_block}\n\n"
        f"QUESTION: {prompt.question}\n\n"
        f"Answer in {answer_lang}. Cite every claim by its source marker like [S1]. "
        f"Quote the Hebrew source text where relevant. "
        f"If the sources do not contain the answer, say so plainly and do not invent."
    )
    messages.append({"role": "user", "content": user})
    return messages


@runtime_checkable
class LLMBackend(Protocol):
    model_id: str
    profile: str         # "local" | "cloud"

    def generate(
        self, prompt: GroundedPrompt, *, lang: str, max_tokens: int, temperature: float
    ) -> LLMResult: ...

    def stream(
        self, prompt: GroundedPrompt, *, lang: str, max_tokens: int, temperature: float
    ) -> Iterator[str]: ...
