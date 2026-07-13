"""Backend-agnostic agentic-retrieval loop.

Any LLM backend can let the model pull its own sources: the model replies with a block that starts
with the exact line `===NEED_SOURCES===` followed by 1–5 search queries instead of a final answer;
the loop retrieves them (via an injected `source_fetcher`), appends them to the job with fresh [S#]
markers, and re-sends — up to MAX_RETRIEVAL_ROUNDS. The loop is transport-agnostic: it drives a
`send(job_md) -> answer|None` callable, so the bridge (file handshake) and cloud/local (a completion
call) share the exact same behaviour.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable

from chavruta.llm.base import GroundedPrompt, SourceBlock

MAX_RETRIEVAL_ROUNDS = int(os.environ.get("CHAVRUTA_BRIDGE_MAX_ROUNDS", "4"))

# Instruction (added to every job) telling the model it may pull more sources itself.
SOURCE_REQUEST_INSTRUCTION = (
    "IF THE SOURCES ARE THIN OR OFF-TOPIC — you may fetch more yourself. Instead of answering, reply "
    "with ONLY a block that starts with the exact line '===NEED_SOURCES===' followed by 1–5 focused "
    "search queries, one per line (Hebrew or English, e.g. a sugya, a ref, a topic). The system will "
    "retrieve them and re-send this job with the extra sources appended. Prefer this over answering "
    "from unrelated sources. When you have enough, write the real answer."
)

_NEED_RE = re.compile(r"^\s*={2,}\s*NEED[ _]SOURCES\s*={2,}\s*$", re.M | re.I)

# The loop's graceful-degrade sentinels (timeout / couldn't-fetch). Callers use is_degrade_message()
# to avoid packaging one of these as a real answer (e.g. a downloadable "lesson" file).
_TIMEOUT_MSG = {"he": "לא התקבלה תשובה מהמודל בזמן. נסה שוב.",
                "en": "No answer from the model in time. Please try again."}
_NOFETCH_MSG = {"he": "לא הצלחתי להשיג מקורות מתאימים דרך הראג. נסה לנסח מחדש או לציין מקור מדויק.",
                "en": "I couldn't retrieve suitable sources via the RAG. "
                      "Try rephrasing or naming a precise source."}
DEGRADE_MESSAGES = frozenset(_TIMEOUT_MSG.values()) | frozenset(_NOFETCH_MSG.values())

# Appended to the job on the FINAL retrieval round to force a real answer out of a model that keeps
# replying ===NEED_SOURCES=== (rather than dead-ending in a degrade when sources were actually found).
_FINAL_ANSWER_NOTE = {
    "he": "\n\n## הוראה אחרונה — חובה\nלא ניתן למשוך מקורות נוספים. כתוב עכשיו את התשובה/השיעור המלא על "
          "סמך המקורות שכבר ניתנו למעלה בלבד. אל תשיב שוב ב-===NEED_SOURCES===.",
    "en": "\n\n## FINAL INSTRUCTION — REQUIRED\nNo more sources can be fetched. Write the full answer/lesson "
          "NOW using ONLY the sources already provided above. Do NOT reply with ===NEED_SOURCES=== again.",
}


def is_degrade_message(text: str) -> bool:
    """True if `text` is one of the loop's graceful-degrade sentinels (or empty) — i.e. not a real
    grounded answer, so it must not be emitted as a lesson file / marked grounded."""
    return not (text or "").strip() or (text or "").strip() in DEGRADE_MESSAGES


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
        queries = parse_need_sources(answer)
        if not queries:
            return answer, fetched              # the model wrote a real answer
        if last_round:
            return answer, fetched              # forced final round — take what it wrote (marker stripped downstream)
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
                    max_tokens: int = 8000) -> tuple[str, list[SourceBlock]]:
    """Run the agentic loop for a completion backend (CloudLLM/LocalLLM): each round sends the whole
    job markdown as one grounded prompt and returns the model's completion. Returns
    (answer, fetched_sources) so the caller aligns citations without any shared per-call state."""
    def _send(job_md: str) -> str | None:
        prompt = GroundedPrompt(system=_REQUEST_SYSTEM, sources=[], question=job_md)
        try:
            # Unlike the bridge's file-poll transport (which returns None on timeout and never
            # raises), a real completion backend raises on any API error / timeout / rate-limit /
            # Ollama-not-running. Treat that like a timeout so the loop degrades gracefully instead
            # of 500-ing the whole request.
            return llm.generate(prompt, lang=lang, max_tokens=max_tokens, temperature=0.3).text or None
        except Exception:
            return None

    return run_agentic_loop(_send, body_md, getattr(llm, "source_fetcher", None), lang)
