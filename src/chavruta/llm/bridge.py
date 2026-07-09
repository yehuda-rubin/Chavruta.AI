"""BridgeLLM — the model is Claude, in the coding session (NO external API).

Same LLMBackend interface, selected by CHAVRUTA_LLM_BACKEND=bridge. Instead of calling any LLM
API, `generate` writes the grounded prompt (question + retrieved sources, with [S#] markers) to a
file under data/llm_bridge/pending/, then waits for the answer to appear under
data/llm_bridge/answers/. Claude (watching the pending folder) reads the sources and writes the
grounded answer there — so the RAG is real and the generation is Claude, with no external API.

The answer must cite by the same [S#] markers so the pipeline can resolve citations.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

from chavruta.llm.base import GroundedPrompt, LLMResult

BRIDGE_DIR = Path(os.environ.get("CHAVRUTA_BRIDGE_DIR", "data/llm_bridge"))
PENDING = BRIDGE_DIR / "pending"
ANSWERS = BRIDGE_DIR / "answers"


class BridgeLLM:
    profile = "bridge"
    model_id = "claude-in-session"

    def __init__(self, timeout: float = 600.0, poll: float = 1.0):
        self.timeout = timeout
        self.poll = poll
        PENDING.mkdir(parents=True, exist_ok=True)
        ANSWERS.mkdir(parents=True, exist_ok=True)

    def _write_job(self, prompt: GroundedPrompt, lang: str) -> str:
        jid = uuid.uuid4().hex[:12]
        lines = [f"# job {jid}", f"lang: {lang}", "", "## QUESTION", prompt.question.strip(), "", "## SOURCES"]
        if prompt.sources:
            for s in prompt.sources:
                who = f" ({s.commentator_id})" if s.commentator_id else ""
                lines += [f"### [{s.marker}] {s.ref}{who}", (s.text or "").strip(), ""]
        else:
            lines += ["(no sources retrieved)", ""]
        lines += [
            "## INSTRUCTIONS FOR CLAUDE",
            f"Write the answer to  data/llm_bridge/answers/{jid}.txt",
            "- Answer ONLY from the SOURCES above; cite every claim by its [S#] marker.",
            "- Quote the Hebrew source text where relevant. Match the question's language.",
            "- If the sources do not contain the answer, say so plainly — do not invent.",
        ]
        (PENDING / f"{jid}.md").write_text("\n".join(lines), encoding="utf-8")
        return jid

    def generate(self, prompt: GroundedPrompt, *, lang: str, max_tokens: int,
                 temperature: float) -> LLMResult:
        jid = self._write_job(prompt, lang)
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
                return LLMResult(text=text, finish_reason="stop")
            time.sleep(self.poll)
            waited += self.poll
        return LLMResult(
            text=("לא התקבלה תשובה מהמודל בזמן. נסה שוב." if lang == "he"
                  else "No answer from the model in time. Please try again."),
            finish_reason="timeout",
        )

    def stream(self, prompt: GroundedPrompt, *, lang: str, max_tokens: int,
               temperature: float) -> Iterator[str]:
        yield self.generate(prompt, lang=lang, max_tokens=max_tokens, temperature=temperature).text

    def request(self, body_md: str) -> str:
        """Low-level bridge: write an arbitrary job (already-formatted markdown) to pending/,
        wait for Claude's answer, return its raw text. Used by the lesson path, which asks Claude
        to write the three lesson files in one delimited answer."""
        jid = uuid.uuid4().hex[:12]
        (PENDING / f"{jid}.md").write_text(f"# lesson job {jid}\n\n{body_md}", encoding="utf-8")
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
        return ""
