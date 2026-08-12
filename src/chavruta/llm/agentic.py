"""Backend-agnostic agentic-retrieval loop.

Any LLM backend can let the model pull its own sources: the model replies with a block that starts
with the exact line `===NEED_SOURCES===` followed by 1–5 search queries instead of a final answer;
the loop retrieves them (via an injected `source_fetcher`), appends them to the job with fresh [S#]
markers, and re-sends — up to MAX_RETRIEVAL_ROUNDS. The loop is transport-agnostic: it drives a
`send(job_md) -> answer|None` callable, so the bridge (file handshake) and cloud/local (a completion
call) share the exact same behaviour.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable

from chavruta.llm.base import GroundedPrompt, SourceBlock

_log = logging.getLogger("chavruta.llm.agentic")

MAX_RETRIEVAL_ROUNDS = int(os.environ.get("CHAVRUTA_BRIDGE_MAX_ROUNDS", "4"))

# Instruction (added to every job) telling the model it may pull more sources itself.
SOURCE_REQUEST_INSTRUCTION = (
    "IF THE SOURCES ARE THIN OR OFF-TOPIC — you may fetch more yourself. Instead of answering, reply "
    "with ONLY a block that starts with the exact line '===NEED_SOURCES===' followed by 1–5 focused "
    "search queries, one per line (Hebrew or English, e.g. a sugya, a ref, a topic). The system will "
    "retrieve them and re-send this job with the extra sources appended. Prefer this over answering "
    "from unrelated sources. When you have enough, write the real answer.\n"
    "WRITE THOSE QUERIES IN THE LANGUAGE OF THE SOURCES, NOT THE LANGUAGE OF THE QUESTION. Search "
    "retrieves by resemblance to the stored text, so a query phrased the way a person asks ('what is "
    "the dispute between Rashi and Tosafot about building the Temple') resembles nothing in the "
    "corpus, while the sugya's own words find it immediately. Use the phrase you expect the source "
    "itself to contain, the technical term, the דיבור המתחיל, or an exact ref. Measured on this "
    "corpus: the question-shaped query did not reach the right Rashi within the top 50 results; the "
    "same source ranked 2nd for a query in its own wording. If you don't know the source's wording, "
    "guess several — each line is a separate search, so vary them rather than rephrasing one idea.\n"
    "WATCH FOR A SPECIFIC TRAP: a question about a MODERN object or activity (a computer, phone, "
    "car, appliance) can retrieve sources that only share a literal word with the question but "
    "address a different, older concept (e.g. a question about playing on a computer retrieving a "
    "sugya about games/jest in general, instead of the halachically operative issue — using an "
    "electrical device). If the sources you were given don't address the real-world thing the "
    "question is actually about, don't conclude 'no source' from them — first request sources on "
    "the underlying halachic category the modern case actually raises (e.g. electricity/muktzeh/"
    "writing for an electronic device, rather than the sugya sharing its surface wording)."
)

_NEED_RE = re.compile(r"^\s*={2,}\s*NEED[ _]SOURCES\s*={2,}\s*$", re.M | re.I)

# The loop's graceful-degrade sentinels (timeout / couldn't-fetch). Callers use is_degrade_message()
# to avoid packaging one of these as a real answer (e.g. a downloadable "lesson" file).
_TIMEOUT_MSG = {"he": "לא התקבלה תשובה מהמודל בזמן. נסה שוב.",
                "en": "No answer from the model in time. Please try again."}
_NOFETCH_MSG = {"he": "לא הצלחתי להשיג מקורות מתאימים דרך הראג. נסה לנסח מחדש או לציין מקור מדויק.",
                "en": "I couldn't retrieve suitable sources via the RAG. "
                      "Try rephrasing or naming a precise source."}
# A misconfigured backend (bad key, bad model id, no credit) is NOT a timeout: retrying can never
# help. Telling the user "try again" hides an operator problem behind a user-facing lie, and it used
# to be indistinguishable from a real timeout in both the UI and the (nonexistent) logs.
_CONFIG_MSG = {"he": "שירות המודל אינו זמין עקב תקלת תצורה בצד השרת. פנייה חוזרת לא תעזור — יש לבדוק "
                     "את הגדרות ה-API בשרת.",
               "en": "The model service is unavailable due to a server-side configuration problem. "
                     "Retrying will not help — the server's API settings need attention."}
# The request hit its whole-request token ceiling before the model committed to an answer.
_BUDGET_MSG = {"he": "התשובה חרגה מתקציב העיבוד המוקצה לבקשה. נסה לצמצם את השאלה או לבקש אורך קצר יותר.",
               "en": "This request exceeded its processing budget. Try narrowing the question or "
                     "asking for a shorter length."}
# The model answered with nothing but its own reasoning. Same user-facing advice as a budget stop —
# from the reader's side the two are the same event, an output allowance spent before an answer
# appeared — but a DIFFERENT line in the log, because the fix is the model's floor, not the question.
_REASONING_MSG = _BUDGET_MSG
DEGRADE_MESSAGES = (frozenset(_TIMEOUT_MSG.values()) | frozenset(_NOFETCH_MSG.values())
                    | frozenset(_CONFIG_MSG.values()) | frozenset(_BUDGET_MSG.values()))

# Appended to the job on the FINAL retrieval round to force a DECISION out of a model that keeps
# replying ===NEED_SOURCES=== (rather than dead-ending in a degrade when sources were actually found).
# The decision is "answer now, from what you have" OR "say plainly it isn't enough" — never a third
# option of asking again, and never silently guessing to fill a gap. Grounding is what keeps a made-up
# or mischaracterizing answer about a real source (or a real named person) from being the easy way out
# of a thin final round (docs/legal/LAWSUIT-EXPOSURE-2026-07-30.md Finding C) — so this must keep the
# honest "not enough to answer" exit open even on the last round, not just on earlier ones.
_FINAL_ANSWER_NOTE = {
    "he": "\n\n## הוראה אחרונה — חובה\nלא ניתן למשוך מקורות נוספים. אם המקורות שכבר ניתנו למעלה מספיקים — "
          "כתוב עכשיו את התשובה/השיעור המלא על סמכם בלבד. אם גם לאחר כל הסבבים המקורות אינם מספיקים "
          "לתשובה אמינה ומבוססת — אל תנחש ואל תמלא את הפער: אמור זאת בפירוש (למשל: \"אין בקורפוס די "
          "מקור כדי לענות על כך באחריות\") במקום לכתוב תשובה לא מעוגנת. בכל מקרה אל תשיב שוב "
          "ב-===NEED_SOURCES===.",
    "en": "\n\n## FINAL INSTRUCTION — REQUIRED\nNo more sources can be fetched. If the sources already "
          "provided above are enough, write the full answer/lesson NOW using ONLY them. If, even after "
          "every round, the sources genuinely do not support a reliable answer, do not guess or fill the "
          "gap — say so plainly (e.g. \"the corpus does not contain enough grounded material to answer "
          "this responsibly\") instead of writing an ungrounded answer. Either way, do NOT reply with "
          "===NEED_SOURCES=== again.",
}


def is_degrade_message(text: str) -> bool:
    """True if `text` is one of the loop's graceful-degrade sentinels (or empty) — i.e. not a real
    grounded answer, so it must not be emitted as a lesson file / marked grounded."""
    return not (text or "").strip() or (text or "").strip() in DEGRADE_MESSAGES


def is_source_request(text: str) -> bool:
    """True if `text` starts a ===NEED_SOURCES=== block at all — regardless of whether it also
    included any usable query lines. Callers must check this BEFORE treating an empty
    parse_need_sources() result as "the model wrote a real answer": a model that emits the marker
    with no queries after it is still asking for sources, just malformed, and must not have its raw
    marker text leak to the user as the final answer (see run_agentic_loop)."""
    return bool(_NEED_RE.search(text or ""))


def parse_need_sources(text: str) -> list[str]:
    """If the answer is a source-request, return its query lines (else [])."""
    m = _NEED_RE.search(text or "")
    if not m:
        return []
    queries: list[str] = []
    for ln in text[m.end():].splitlines():
        s = ln.strip(" \t‏‎-•*>·").strip()
        if not s:
            continue
        if s.startswith("==="):        # a following delimiter ends the block
            break
        queries.append(s)
    return queries[:5]


def strip_source_request_marker(text: str) -> str:
    """Defensive backstop: remove a bare ===NEED_SOURCES=== block from text that is about to be
    shown to a user as a final answer (e.g. a forced last round that still degenerated into the
    marker). Real answers never contain this marker, so this is a no-op on them."""
    if not _NEED_RE.search(text or ""):
        return text
    return _NEED_RE.sub("", text).strip()


def max_marker(job_md: str) -> int:
    # Count ONLY source-header markers — every source block is emitted as `### [S#] <ref>` at line
    # start (api job builders, bridge._write_job_md, append_sources below). A bare `[S30]` inside the
    # question / conversation history / a source body must NOT count: it would inflate the append
    # offset and knock the caller's positional `hits + fetched` citation mapping out of alignment
    # (misattributing or dropping the model's cited source).
    nums = [int(n) for n in re.findall(r"(?m)^\s*#{1,4}\s*\[\s*S(\d+)\s*\]", job_md)]
    return max(nums) if nums else 0


def append_sources(job_md: str, sources: list[SourceBlock], start_n: int) -> str:
    lines = ["", "## ADDITIONAL SOURCES (retrieved at your request)"]
    for i, s in enumerate(sources, start_n + 1):
        who = f" ({s.commentator_id})" if getattr(s, "commentator_id", None) else ""
        lines += [f"### [S{i}] {s.ref}{who}", (s.text or "").strip(), ""]
    lines += [
        "## NOTE",
        "The sources you asked for were retrieved and added above. Now write the full answer "
        "(or send another ===NEED_SOURCES=== block if you still need more).",
    ]
    return job_md + "\n" + "\n".join(lines)


def run_agentic_loop(send: Callable[[str], str | None], job_md: str,
                     source_fetcher: Callable[[list[str]], list[SourceBlock]] | None,
                     lang: str) -> tuple[str, list[SourceBlock]]:
    """Drive the agentic-retrieval loop over `send`. Returns (final_answer, fetched_sources) — the
    fetched sources are in [S#] order (continuing after the job's original markers) so the caller can
    align its citation mapping. `send(job_md)` returns the model's answer text, or None on timeout."""
    fetched: list[SourceBlock] = []
    for round_i in range(MAX_RETRIEVAL_ROUNDS):
        last_round = round_i == MAX_RETRIEVAL_ROUNDS - 1
        # On the FINAL round, append a hard instruction so a model that keeps over-asking commits to
        # writing from the sources it already has — otherwise it dead-ends in a "couldn't get sources"
        # degrade even though good sources were retrieved (observed with strong models on scattered
        # topics). A model that asked once and got sources is unaffected.
        answer = send(job_md + _FINAL_ANSWER_NOTE.get(lang, _FINAL_ANSWER_NOTE["en"]) if last_round else job_md)
        if answer is None:
            return _TIMEOUT_MSG.get(lang, _TIMEOUT_MSG["en"]), fetched
        if not is_source_request(answer):
            return answer, fetched              # the model wrote a real answer
        if last_round:
            # Forced final round: take what it wrote, minus a bare marker it may have relapsed into
            # despite the instruction not to — never show the raw ===NEED_SOURCES=== line to a user.
            return strip_source_request_marker(answer) or _NOFETCH_MSG.get(lang, _NOFETCH_MSG["en"]), fetched
        queries = parse_need_sources(answer)
        if not queries:
            # The model started a source-request block but gave no usable query lines — nothing to
            # fetch. Ask it to either supply real queries or answer now, and spend a round on that
            # rather than returning its bare, meaningless marker as if it were the final answer.
            job_md = job_md + (
                "\n\n## NOTE\nYour previous reply started ===NEED_SOURCES=== but listed no search "
                "queries after it. Either list 1-5 focused search queries (one per line) right after "
                "that line, or answer now using the sources already given.")
            continue
        if source_fetcher is None:              # asked, rounds remain, but there is no fetcher to call
            return _NOFETCH_MSG.get(lang, _NOFETCH_MSG["en"]), fetched
        try:
            more = source_fetcher(queries) or []
        except Exception:
            more = []
        if not more:
            job_md = job_md + (
                "\n\n## NOTE\nNo additional sources were found for your queries. Answer with the "
                "sources already given, or say plainly that the corpus lacks the material.")
            continue
        job_md = append_sources(job_md, more, max_marker(job_md))
        fetched.extend(more)       # in [S#] order, for the caller's citation mapping
    return "", fetched


# ── generic transport for a chat/completion backend (cloud/local) ────────────────────────────────
_REQUEST_SYSTEM = ("You are a grounded Torah study assistant. Follow the job below exactly — it "
                   "contains the sources (each tagged [S#]) and the instructions. Cite by [S#].")


def agentic_request(llm, body_md: str, *, lang: str = "he",
                    max_tokens: int = 8000,
                    token_budget: int | None = None) -> tuple[str, list[SourceBlock]]:
    """Run the agentic loop for a completion backend (CloudLLM): each round sends the whole
    job markdown as one grounded prompt and returns the model's completion. Returns
    (answer, fetched_sources) so the caller aligns citations without any shared per-call state.

    `max_tokens` bounds ONE round's output. `token_budget` bounds the request's TOTAL output across
    every round — the thing that actually determines what a question costs, since the loop re-sends
    the whole growing job up to MAX_RETRIEVAL_ROUNDS times. Without it, per-round caps multiply.

    Token spend is not returned: every round's call meters itself in the backend (llm/metering.py),
    so the whole loop is already counted by the time this returns.
    """
    # Imported here, not at module scope: cloud.py imports agentic_request, so a top-level import
    # back into cloud would be circular.
    from chavruta.llm.cloud import LLMConfigError, LLMEmptyAnswerError

    state: dict = {"out_tokens": 0, "prompt_tokens": 0}

    def _send(job_md: str) -> str | None:
        # Never let a round overshoot what's left of the whole-request budget.
        room = max_tokens
        if token_budget is not None:
            room = min(max_tokens, max(0, token_budget - state["out_tokens"]))
            if room <= 0:
                _log.warning("agentic: token budget %d exhausted (spent %d out); stopping",
                             token_budget, state["out_tokens"])
                state["budget_exhausted"] = True
                return None
        prompt = GroundedPrompt(system=_REQUEST_SYSTEM, sources=[], question=job_md)
        try:
            # Unlike the bridge's file-poll transport (which returns None on timeout and never
            # raises), a real completion backend raises on any API error / timeout / rate-limit.
            # Degrade gracefully rather than 500-ing the whole request — but never silently: a
            # swallowed exception here meant a wrong API key looked exactly like a slow model, in
            # the UI and in the logs, with nothing to alert on.
            res = llm.generate(prompt, lang=lang, max_tokens=room, temperature=0.3)
        except LLMConfigError as exc:
            _log.error("agentic: unrecoverable LLM config error, aborting loop: %s", exc)
            state["config_error"] = True
            return None
        except LLMEmptyAnswerError as exc:
            # Not transient: the same prompt at the same budget will spend it on reasoning again, so
            # retrying only buys another wait. Abort the loop and log what to change — this is the
            # failure a reasoning model produces on a budget sized for a model that answers directly.
            _log.error("agentic: model returned reasoning but no answer, aborting loop: %s", exc)
            state["empty_answer"] = True
            return None
        except Exception as exc:
            _log.warning("agentic: transient LLM failure, degrading this round: %s", exc, exc_info=True)
            return None
        state["out_tokens"] += getattr(res, "completion_tokens", 0) or 0
        state["prompt_tokens"] += getattr(res, "prompt_tokens", 0) or 0
        return res.text or None

    answer, fetched = run_agentic_loop(_send, body_md, getattr(llm, "source_fetcher", None), lang)
    _log.info("agentic request done: rounds_out_tokens=%d rounds_prompt_tokens=%d budget=%s fetched=%d",
              state["out_tokens"], state["prompt_tokens"], token_budget, len(fetched))
    if state.get("config_error"):
        return _CONFIG_MSG.get(lang, _CONFIG_MSG["en"]), fetched
    # A budget stop mid-loop leaves no answer text; say so rather than returning the timeout lie.
    if (state.get("budget_exhausted") or state.get("empty_answer")) and not (answer or "").strip():
        return _BUDGET_MSG.get(lang, _BUDGET_MSG["en"]), fetched
    return answer, fetched
