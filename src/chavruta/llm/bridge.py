"""BridgeLLM — the model is Claude, in the coding session (NO external API).

Same LLMBackend interface, selected by CHAVRUTA_LLM_BACKEND=bridge. Instead of calling any LLM
API, `generate` writes the grounded prompt (question + retrieved sources, with [S#] markers) to a
file under data/llm_bridge/pending/, then waits for the answer to appear under
data/llm_bridge/answers/. Claude (watching the pending folder) reads the sources and writes the
grounded answer there — so the RAG is real and the generation is Claude, with no external API.

The answer must cite by the same [S#] markers so the pipeline can resolve citations.

Agentic retrieval: on ANY job, the model may reply with a block that starts with the exact line
`===NEED_SOURCES===` followed by 1–5 search queries (one per line) instead of a final answer. If a
`source_fetcher` is wired (the pipeline injects one), the bridge retrieves those queries, appends the
new sources to the job with fresh [S#] markers, and re-issues the job — letting the model pull better
material when the initial retrieval was thin or off-topic. Bounded by MAX_RETRIEVAL_ROUNDS.
"""

from __future__ import annotations

import os
import re
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

from chavruta.llm.base import GroundedPrompt, LLMResult, SourceBlock

BRIDGE_DIR = Path(os.environ.get("CHAVRUTA_BRIDGE_DIR", "data/llm_bridge"))
PENDING = BRIDGE_DIR / "pending"
ANSWERS = BRIDGE_DIR / "answers"

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


def _parse_need_sources(text: str) -> list[str]:
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


def _max_marker(job_md: str) -> int:
    nums = [int(n) for n in re.findall(r"\[\s*S(\d+)\s*\]", job_md)]
    return max(nums) if nums else 0


def _append_sources(job_md: str, sources: list[SourceBlock], start_n: int) -> str:
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


class BridgeLLM:
    profile = "bridge"
    model_id = "claude-in-session"

    def __init__(self, timeout: float = 600.0, poll: float = 1.0,
                 source_fetcher: Callable[[list[str]], list[SourceBlock]] | None = None):
        self.timeout = timeout
        self.poll = poll
        # Injected by the pipeline: maps the model's follow-up queries → fresh retrieved sources.
        self.source_fetcher = source_fetcher
        PENDING.mkdir(parents=True, exist_ok=True)
        ANSWERS.mkdir(parents=True, exist_ok=True)

    # ── job dispatch with the agentic-retrieval loop ─────────────────────────────
    def _await(self, jid: str) -> str | None:
        """Poll for the answer file; return its text, or None on timeout. Cleans up both files."""
        answer_path = ANSWERS / f"{jid}.txt"
        waited = 0.0
        while waited < self.timeout:
            if answer_path.exists():
                text = answer_path.read_text(encoding="utf-8").strip()
                for p in (PENDING / f"{jid}.md", answer_path):
                    try:
                        p.unlink()
                    except OSError:
                        pass
                return text
            time.sleep(self.poll)
            waited += self.poll
        try:
            (PENDING / f"{jid}.md").unlink()
        except OSError:
            pass
        return None

    def _dispatch(self, header: str, job_md: str, lang: str) -> str:
        """Write the job, wait, and run the agentic-retrieval loop until the model gives a real
        answer (or we run out of rounds / the fetcher yields nothing).

        Sources fetched during the loop are recorded (in [S#] order, continuing after the job's
        original markers) on `self.fetched_sources`, so the caller can align its citation mapping."""
        self.fetched_sources: list[SourceBlock] = []
        for round_i in range(MAX_RETRIEVAL_ROUNDS):
            jid = uuid.uuid4().hex[:12]
            (PENDING / f"{jid}.md").write_text(f"{header} {jid}\n\n{job_md}", encoding="utf-8")
            answer = self._await(jid)
            if answer is None:
                return ("לא התקבלה תשובה מהמודל בזמן. נסה שוב." if lang == "he"
                        else "No answer from the model in time. Please try again.")
            queries = _parse_need_sources(answer)
            last_round = round_i == MAX_RETRIEVAL_ROUNDS - 1
            if not queries or self.source_fetcher is None or last_round:
                if queries:            # asked but we can't fetch again — don't surface a raw marker
                    return ("לא הצלחתי להשיג מקורות מתאימים דרך הראג. נסה לנסח מחדש או לציין מקור מדויק."
                            if lang == "he"
                            else "I couldn't retrieve suitable sources via the RAG. "
                                 "Try rephrasing or naming a precise source.")
                return answer
            try:
                more = self.source_fetcher(queries) or []
            except Exception:
                more = []
            if not more:
                # nothing new surfaced — let the model answer with what it has next round
                job_md = job_md + (
                    "\n\n## NOTE\nNo additional sources were found for your queries. Answer with the "
                    "sources already given, or say plainly that the corpus lacks the material.")
                continue
            job_md = _append_sources(job_md, more, _max_marker(job_md))
            self.fetched_sources.extend(more)   # in [S#] order, for the caller's citation mapping
        return ""

    # ── LLMBackend interface ─────────────────────────────────────────────────────
    def _write_job_md(self, prompt: GroundedPrompt) -> str:
        lines = ["## QUESTION", prompt.question.strip(), "", "## SOURCES"]
        if prompt.sources:
            for s in prompt.sources:
                who = f" ({s.commentator_id})" if s.commentator_id else ""
                lines += [f"### [{s.marker}] {s.ref}{who}", (s.text or "").strip(), ""]
        else:
            lines += ["(no sources retrieved)", ""]
        lines += [
            "## INSTRUCTIONS FOR CLAUDE",
            "- Answer ONLY from the SOURCES above; cite every claim by its [S#] marker.",
            "- Quote the Hebrew source text where relevant. Match the question's language.",
            "- If the sources do not contain the answer, say so plainly — do not invent.",
            SOURCE_REQUEST_INSTRUCTION,
        ]
        return "\n".join(lines)

    def generate(self, prompt: GroundedPrompt, *, lang: str, max_tokens: int,
                 temperature: float) -> LLMResult:
        text = self._dispatch("# job", self._write_job_md(prompt), lang)
        return LLMResult(text=text, finish_reason="stop" if text else "timeout")

    def stream(self, prompt: GroundedPrompt, *, lang: str, max_tokens: int,
               temperature: float) -> Iterator[str]:
        yield self.generate(prompt, lang=lang, max_tokens=max_tokens, temperature=temperature).text

    def request(self, body_md: str, *, lang: str = "he") -> str:
        """Low-level bridge: write an arbitrary already-formatted job (markdown) and return Claude's
        raw answer. Used by the lesson / chavruta paths. Runs the same agentic-retrieval loop."""
        return self._dispatch("# lesson job", body_md, lang)
