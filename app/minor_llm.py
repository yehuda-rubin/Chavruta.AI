"""Which model provider may read a MINOR's text (spec 009 R8, T050).

One answer, used by both the crisis classifier (`app/crisis_gate.py`) and generation (`app/api.py`):
the preset the operator named in CHAVRUTA_MINOR_LLM_PRESET, with the key in CHAVRUTA_MINOR_LLM_API_KEY.
Unset, unknown, not in APPROVED_MINOR_PRESETS, keyless, or hosted on Nebius (Services Agreement 4.1.6 treats a minor's personal data as
sensitive and it has not been approved) means NO provider: callers fail closed, they never fall back to
the default backend.

Pure resolution here; building a client is the caller's job (the classifier wants a 10 s one-shot, the
answer path wants the pipeline's timeouts and source fetcher).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

NOT_APPROVED_HOSTS = ("nebius",)          # providers that must never read a minor's text

# The ONLY presets allowed to read a minor's text. EMPTY today, on purpose: a preset is added here only
# after its provider has confirmed IN WRITING that it supports minors' data, does not train on it, and
# that its retention terms are acceptable. That is a founder decision, not a code decision. Naming a
# preset in CHAVRUTA_MINOR_LLM_PRESET is not enough (a free tier such as gemini trains on its input).
APPROVED_MINOR_PRESETS: frozenset[str] = frozenset()


@dataclass(frozen=True)
class MinorBackend:
    name: str
    model: str
    base_url: str
    api_key: str
    min_output_tokens: int = 0


def approved_backend() -> tuple[MinorBackend | None, str]:
    """(backend, "") when a minor-approved provider is configured, else (None, why not)."""
    name = os.environ.get("CHAVRUTA_MINOR_LLM_PRESET", "").strip()
    if not name:
        return None, "CHAVRUTA_MINOR_LLM_PRESET not set"
    if name.lower() not in APPROVED_MINOR_PRESETS:
        return None, "preset is not in APPROVED_MINOR_PRESETS (no written provider approval for minors)"
    try:
        from chavruta.llm.presets import resolve

        preset = resolve(name)
    except Exception:
        return None, "preset could not be built"
    key = os.environ.get("CHAVRUTA_MINOR_LLM_API_KEY", "").strip()
    if preset is None or not key:
        return None, "preset unknown or no CHAVRUTA_MINOR_LLM_API_KEY"
    if any(h in preset.base_url.lower() for h in NOT_APPROVED_HOSTS):
        return None, "preset is hosted by a provider not approved for minors"
    return MinorBackend(name.lower(), preset.model, preset.base_url, key, preset.min_output_tokens), ""
