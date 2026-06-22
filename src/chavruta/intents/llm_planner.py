"""LLM query planner (Phase 5, spec 002-query-understanding) — OPTIONAL, flag-gated.

The heuristic router is fast, offline, and deterministic, but it cannot resolve every
indirect phrasing. When `CHAVRUTA_QUERY_PLANNER=llm`, this planner runs as a *fallback*
(only when the heuristics found no explicit ref): one cheap LLM call extracts structured
hints — refs, commentators, intent — as JSON, which the router merges in. Default off, so
the offline/deterministic path (Principle II) is unchanged unless explicitly enabled.
"""

from __future__ import annotations

import json
import re

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

_SYSTEM = (
    "You extract structured retrieval hints from a Jewish-texts study question. "
    "Return ONLY a JSON object with keys: "
    '"refs" (list of canonical Sefaria refs in dotted form, e.g. "Genesis.1.1", '
    '"Bava_Metzia.2a"; resolve indirect references like "the first verse of the Torah" '
    '→ "Genesis.1.1"), "commentators" (list of ids from: rashi, ramban, ibn_ezra, radak, '
    "sforno, rashbam, or_hachaim, malbim, onkelos), and "
    '"intent" (one of: qa, explain, compare, lesson). Use [] when unsure. No prose.'
)


class LLMQueryPlanner:
    def __init__(self, model_id: str, base_url: str, api_key: str):
        self.model_id = model_id
        self.base_url = base_url
        self.api_key = api_key
        self._client = None  # lazy

    def _client_(self):
        if self._client is None:
            from openai import OpenAI  # lazy
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        return self._client

    def plan(self, text: str) -> dict:
        """Return {"refs": [...], "commentators": [...], "intent": str|None}.

        Never raises — on any failure returns empty hints so the request falls back to
        the heuristic result.
        """
        try:
            resp = self._client_().chat.completions.create(
                model=self.model_id,
                messages=[{"role": "system", "content": _SYSTEM},
                          {"role": "user", "content": text}],
                temperature=0.0,
                max_tokens=256,
            )
            return _parse(resp.choices[0].message.content or "")
        except Exception:
            return {"refs": [], "commentators": [], "intent": None}


def _parse(raw: str) -> dict:
    m = _JSON_RE.search(raw)
    if not m:
        return {"refs": [], "commentators": [], "intent": None}
    try:
        data = json.loads(m.group(0))
    except (ValueError, TypeError):
        return {"refs": [], "commentators": [], "intent": None}
    refs = [str(r) for r in data.get("refs", []) if isinstance(r, str)]
    comms = [str(c) for c in data.get("commentators", []) if isinstance(c, str)]
    intent = data.get("intent") if isinstance(data.get("intent"), str) else None
    return {"refs": refs, "commentators": comms, "intent": intent}
