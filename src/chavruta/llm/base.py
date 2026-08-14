"""LLMBackend interface (contracts/llm-backend.md).

Generates the answer from an already-built, source-grounded prompt. Two backends implement this
interface, chosen by config: CloudLLM (the Nebius API — default) and BridgeLLM (Claude answering
in-session, no external API). Grounding is enforced by the pipeline, not trusted to the model alone.
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
    # Everything below is for the READER, not the model: the model only ever sees `text`.
    # A source the agentic loop fetched becomes a SourceBlock and is then rendered on the lesson
    # source sheet exactly like a first-round hit — so whatever a RankedHit carries for display and
    # rights has to survive the conversion. It did not: the sheet fell back to the combined
    # Hebrew+English blob and printed every self-fetched source twice, and its licence column read
    # "unknown" for all of them (reported 2026-08-12). With ~75% of requests reaching a second
    # retrieval round, that was most sources on most sheets.
    text_he: str = ""
    text_en: str = ""
    deep_link: str = ""
    license: str = ""
    version_title: str = ""


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
    # Caught live (2026-08-05): a one-shot non-QA call (rewrite this sentence; classify yes/no) sent
    # through the normal QA template still gets wrapped in "המקורות (הידע היחיד המותר לך)... אם אין
    # תשובה במקורות — אמור זאת ואל תמציא" — and the model sometimes echoes that framing back as if it
    # were content, especially with sources=[] ("no sources retrieved"). bare=True skips the QA
    # template entirely: `question` goes to the model as a plain instruction, nothing wrapped around
    # it. Use this for anything that isn't itself a grounded-answer request.
    bare: bool = False


@dataclass
class LLMResult:
    text: str
    finish_reason: str = "stop"
    # Sources the model pulled itself during agentic retrieval (===NEED_SOURCES===), in [S#] order.
    # Returned per-call (never stashed on the shared backend) so callers align citations race-free.
    fetched_sources: list = field(default_factory=list)
    # Actual tokens billed for this call, when the backend reports them (the bridge does not).
    # Lets the agentic loop enforce a CUMULATIVE budget on real numbers rather than an estimate.
    prompt_tokens: int = 0
    completion_tokens: int = 0


def render_messages(prompt: GroundedPrompt, lang: str) -> list[dict]:
    """Render a GroundedPrompt into OpenAI/Ollama chat messages.

    The system message carries the grounding rules. The sources are presented as the ONLY
    knowledge the model may use, each tagged with its marker so the model cites by marker.

    prompt.bare skips all of that (see its docstring) — `question` goes out as a plain user message,
    for one-shot calls that aren't themselves a grounded-answer request.
    """
    messages: list[dict] = [{"role": "system", "content": prompt.system}]
    for turn in prompt.history:
        messages.append({"role": turn.role, "content": turn.text})

    if prompt.bare:
        messages.append({"role": "user", "content": prompt.question})
        return messages

    if prompt.sources:
        # In Hebrew, lead each source with its HEBREW name. Without it there was no way for a source
        # name to reach the reader at all, and a user said so on 2026-08-14: he asked where an
        # answer's quotes came from and got a list of quotes attributed to nothing.
        #
        # The squeeze was structural, not a prompt-wording problem. The model was handed
        # 'Birkat_Asher_on_Torah,_Deuteronomy.18.11.2' and told to answer in pure Hebrew — so naming
        # the source made the sentence trip `_has_bleed`, and `_fix_bleeding_sentences` rewrote it to
        # take the Latin out again. The only citation channel left was the [S#] marker, which is
        # stripped before display by design. Every route to the reader was closed.
        #
        # The English ref stays on the line: it is what `enforce_citations` and the source sheet key
        # on, and a model that wants to be precise can still copy it. The Hebrew name is what it can
        # actually say out loud in a Hebrew answer.
        from chavruta.corpus.refs import hebrew_display_ref   # local: keeps llm/ free of a corpus dep

        lines = []
        for s in prompt.sources:
            who = f" ({s.commentator_id})" if s.commentator_id else ""
            name = (hebrew_display_ref(s.ref) or "") if lang == "he" else ""
            label = f"{name} — {s.ref}" if name else s.ref
            lines.append(f"[{s.marker}] {label}{who}:\n{s.text}")
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
            f"single terse sentence. Write the explanation in English (you may quote the Hebrew source text), "
            f"but do NOT mix in stray words from other languages (no Chinese/Russian/etc.). Cite every claim by "
            f"its source marker like [S1]. If the sources do not contain the answer, say so plainly and do not invent."
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

    def request(self, body_md: str, *, lang: str = "he",
                token_budget: int | None = None) -> tuple[str, list[SourceBlock]]:
        """Answer a pre-formatted job (markdown) — the lesson/chavruta path — running the agentic
        loop. Returns (answer, fetched_sources) so callers align citations without shared state.

        token_budget caps TOTAL output tokens across all agentic rounds (None = uncapped). Backends
        that don't bill tokens (bridge) may ignore it.
        """
        ...
