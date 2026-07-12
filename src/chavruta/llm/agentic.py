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
    nums = [int(n) for n in re.findall(r"\[\s*S(\d+)\s*\]", job_md)]
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
        answer = send(job_md)
        if answer is None:
            return _TIMEOUT_MSG.get(lang, _TIMEOUT_MSG["en"]), fetched
        queries = parse_need_sources(answer)
        last_round = round_i == MAX_RETRIEVAL_ROUNDS - 1
        if not queries or source_fetcher is None or last_round:
            if queries:            # asked but we can't fetch again — don't surface a raw marker
                return _NOFETCH_MSG.get(lang, _NOFETCH_MSG["en"]), fetched
            return answer, fetched
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
