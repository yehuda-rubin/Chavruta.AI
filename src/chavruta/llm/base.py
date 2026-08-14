"""LLMBackend interface (contracts/llm-backend.md).

Generates the answer from an already-built, source-grounded prompt. Two backends implement this
interface, chosen by config: CloudLLM (the Nebius API — default) and BridgeLLM (Claude answering
in-session, no external API). Grounding is enforced by the pipeline, not trusted to the model alone.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# Whether this request should ask the model to close with its own list of the works it used, behind
# the HHH sentinel (app/api.py::_split_source_note cuts it back out). A ContextVar rather than a
# parameter because `render_messages` is reached through build_prompt, the pipeline, the agentic
# loop and both backends — threading a display flag through all of that would put a presentation
# concern into five signatures that are otherwise about grounding.
#
# Set and reset per request in app/api.py. It is read on the request's own thread, before any
# fan-out; see llm/metering.py for the one place where a ContextVar and a thread pool do meet, and
# what that cost.
_SOURCE_NOTE: ContextVar[bool] = ContextVar("chavruta_source_note", default=False)


def set_source_note(on: bool):
    """Enable/disable the trailing source list for this request. Returns a reset token."""
    return _SOURCE_NOTE.set(bool(on))


def reset_source_note(token) -> None:
    _SOURCE_NOTE.reset(token)


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
        # Imported here, not at module scope, to keep llm/ free of a hard dependency on corpus/.
        from chavruta.corpus.refs import hebrew_display_ref

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
        if _SOURCE_NOTE.get():
            # Asked for AFTER the answer, and cut back out before display. The reader gets it beside
            # the sources; the model gets somewhere to name works without breaking the Hebrew-only
            # rule mid-sentence. Ordered oldest-first because that is what a learner asked for on
            # 2026-08-14 — "סדר בצורה כרונולוגית לפי המקור הקדום ביותר ותן קצת מידע על כל ספר" —
            # and the model can order what it was given even where retrieval ranking cannot yet.
            # Names ONLY. The first version asked for the author and a sentence about each work, and
            # the model invented all of it: on one live answer it gave the Ben Ish Chai's commentary
            # to a "רבי יעקב חיים זילברשטיין", and turned parashat Eikev into a parasha called
            # "איקה". Presented as a tidy metadata block, a reader takes that for fact — which is
            # exactly the invention this product exists not to commit, dressed as a citation.
            #
            # The model does not know these works' authorship; it knows the text it was handed. So
            # it is asked for the one thing it was handed: the name, copied. Anything richer needs a
            # curated table, not a language model.
            # Positive and concrete. A first version asked for the author and a description, and the
            # model invented both — the Ben Ish Chai's commentary attributed to a "רבי יעקב חיים
            # זילברשטיין", parashat Eikev turned into a parasha called "איקה". A second version
            # forbade all of that in a row of negatives, and the model responded by omitting the
            # section altogether. So: say what to write, show the shape, and put the one prohibition
            # last.
            user += (
                "\n\nחובה לסיים כך: שורה שבה כתוב HHH בלבד, ומתחתיה שורה לכל מקור שהשתמשת בו "
                "בפועל, מהקדום למאוחר, ובה שם החיבור בלבד — מועתק מרשימת המקורות שלמעלה. לדוגמה:\n"
                "HHH\n"
                "בבא מציעא 2.\n"
                "רש\"י על בראשית 1:1\n"
                "אל תוסיף מחבר, תאריך או תיאור, וגם לא חיבור שלא הופיע ברשימה שקיבלת."
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
