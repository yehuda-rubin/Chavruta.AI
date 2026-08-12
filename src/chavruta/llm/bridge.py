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
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

from chavruta.llm import metering
from chavruta.llm.agentic import (  # noqa: F401 — re-exported for back-compat
    MAX_RETRIEVAL_ROUNDS,
    SOURCE_REQUEST_INSTRUCTION,
    run_agentic_loop,
)
from chavruta.llm.base import GroundedPrompt, LLMResult, SourceBlock

BRIDGE_DIR = Path(os.environ.get("CHAVRUTA_BRIDGE_DIR", "data/llm_bridge"))
PENDING = BRIDGE_DIR / "pending"
ANSWERS = BRIDGE_DIR / "answers"


def _estimate_tokens(text: str) -> int:
    """Rough token count for text this backend never gets a real usage figure for.

    ~3.5 characters per token: Hebrew tokenizes worse than English on the multilingual vocabularies
    these models use, so the usual 4.0 rule of thumb undercounts here. Deliberately an over-estimate
    — for a quota, charging slightly too much is a smaller error than serving compute for free.
    """
    return int(len(text or "") / 3.5)


class BridgeLLM:
    profile = "bridge"
    model_id = "claude-in-session"
    # This backend answers through ONE human-in-the-loop job at a time: a job is written to a file,
    # Claude reads it in-session, and the answer comes back on a matching path. Two overlapping calls
    # would put two jobs in front of one reader with no way to tell which answer belongs to which.
    # Callers that would otherwise fan work out in threads (see api._fix_bleeding_sentences) check
    # this flag and stay serial. Cloud backends carry no such flag — their clients are thread-safe.
    serial_only = True

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

    def _dispatch(self, header: str, job_md: str, lang: str):
        """Run the shared agentic-retrieval loop over the file-handshake transport: each round writes
        a fresh job to pending/ and waits for the answer. Returns (answer, fetched_sources) — fetched
        in [S#] order — so the caller aligns citations without any shared per-call state."""
        def _send(jmd: str) -> str | None:
            jid = uuid.uuid4().hex[:12]
            (PENDING / f"{jid}.md").write_text(f"{header} {jid}\n\n{jmd}", encoding="utf-8")
            return self._await(jid)

        return run_agentic_loop(_send, job_md, self.source_fetcher, lang)

    # ── LLMBackend interface ─────────────────────────────────────────────────────
    def _write_job_md(self, prompt: GroundedPrompt) -> str:
        # See GroundedPrompt.bare: a one-shot non-QA call (rewrite/classify) skips the "## SOURCES /
        # ## INSTRUCTIONS: answer only from sources, cite [S#]" framing entirely — that framing is
        # exactly what a model can echo back when the actual task isn't answering a grounded question.
        if prompt.bare:
            return prompt.question.strip()
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
        job_md = self._write_job_md(prompt)
        text, fetched = self._dispatch("# job", job_md, lang)
        metering.record(_estimate_tokens(job_md), _estimate_tokens(text or ""))   # see request()
        return LLMResult(text=text, finish_reason="stop" if text else "timeout", fetched_sources=fetched)

    def stream(self, prompt: GroundedPrompt, *, lang: str, max_tokens: int,
               temperature: float) -> Iterator[str]:
        yield self.generate(prompt, lang=lang, max_tokens=max_tokens, temperature=temperature).text

    def request(self, body_md: str, *, lang: str = "he", token_budget: int | None = None):
        """Low-level bridge: write an arbitrary already-formatted job (markdown) and return Claude's
        (answer, fetched_sources). Used by the lesson / chavruta paths. Runs the agentic loop.

        token_budget is accepted for interface parity and ignored: this backend answers in-session
        and bills no provider tokens, so there is nothing to meter for COST.

        It still meters for QUOTA, from an estimate — the account allowance is denominated in tokens,
        so recording nothing would make every bridge request free and the quota silently inert in
        bridge mode. A metering difference between backends is exactly the kind of thing nobody
        notices until the bridge is running in front of users.
        """
        answer, fetched = self._dispatch("# lesson job", body_md, lang)
        metering.record(_estimate_tokens(body_md), _estimate_tokens(answer or ""))
        return answer, fetched
