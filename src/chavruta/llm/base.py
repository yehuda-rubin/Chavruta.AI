"""LLMBackend interface (contracts/llm-backend.md).

Generates the answer from an already-built, source-grounded prompt. The dual-model strategy
lives here: LocalLLM (DictaLM via Ollama) and CloudLLM (Nebius) implement the same interface,
chosen by config. Grounding is enforced by the pipeline, not trusted to the model alone.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
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
    # Sources the model pulled itself during agentic retrieval (===NEED_SOURCES===), in [S#] order.
    # Returned per-call (never stashed on the shared backend) so callers align citations race-free.
    fetched_sources: list = field(default_factory=list)


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

    if lang == "he":
        user = (
            f"המקורות (הידע היחיד המותר לך):\n{sources_block}\n\n"
            f"השאלה: {prompt.question}\n\n"
            f"ענה בעברית בצורה ברורה, מלאה ומנומקת — הסבר את התשובה ופַתח אותה, אל תסתפק במשפט יבש אחד. "
            f"כתוב אך ורק בעברית תקנית, ללא מילים בשפה זרה. "
            f"צרף לכל טענה את סימון המקור, למשל [S1]. "
            f"צטט את לשון המקור כשרלוונטי. אם אין תשובה במקורות — אמור זאת ואל תמציא."
        )
    else:
        user = (
            f"SOURCES (the only knowledge you may use):\n{sources_block}\n\n"
            f"QUESTION: {prompt.question}\n\n"
            f"Answer in English clearly and fully — explain and develop your answer, do not reply with a "
            f"single terse sentence. Cite every claim by its source marker like [S1]. Quote the Hebrew "
            f"source text where relevant. If the sources do not contain the answer, say so plainly and do not invent."
        )
    messages.append({"role": "user", "content": user})
    return messages


@runtime_checkable
class LLMBackend(Protocol):
    model_id: str
    profile: str         # "local" | "cloud" | "bridge"
    # Agentic retrieval: the pipeline injects a fetcher; the model may pull its own sources via a
    # ===NEED_SOURCES=== block (see chavruta.llm.agentic). Part of the contract, not duck-typed.
    source_fetcher: Callable[[list[str]], list[SourceBlock]] | None

    def generate(
        self, prompt: GroundedPrompt, *, lang: str, max_tokens: int, temperature: float
    ) -> LLMResult: ...

    def stream(
        self, prompt: GroundedPrompt, *, lang: str, max_tokens: int, temperature: float
    ) -> Iterator[str]: ...

    def request(self, body_md: str, *, lang: str = "he") -> tuple[str, list[SourceBlock]]:
        """Answer a pre-formatted job (markdown) — the lesson/chavruta path — running the agentic
        loop. Returns (answer, fetched_sources) so callers align citations without shared state."""
        ...
