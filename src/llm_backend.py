# -*- coding: utf-8 -*-
"""
llm_backend.py — שכבת LLM אגנוסטית לפריסה (Decision D3/D5).
─────────────────────────────────────────────────────────────────────────────
ממשק אחיד generate(messages) עם שני backends, נבחרים דרך משתנה סביבה LLM_BACKEND:

  • "ollama"  (ברירת מחדל) — מקומי, רץ לגמרי OFFLINE. לשימוש הכללי שלך.
  • "nebius"  — Nebius Token Factory, API תואם-OpenAI, serverless pay-per-token. לתחרות.

החלפה בין הפרופילים = משתנה סביבה אחד. אותו קוד RAG מעליו.

env:
  LLM_BACKEND      = ollama | nebius           (ברירת מחדל: ollama)
  NEBIUS_API_KEY   = <key>                      (נדרש ל-nebius)
  NEBIUS_MODEL     = Qwen/Qwen3-235B-A22B       (ניתן לשנות)
  NEBIUS_BASE_URL  = https://api.tokenfactory.nebius.com/v1/
"""

from __future__ import annotations
import os

try:
    import config  # נתיבים/הגדרות מרכזיים
    _OLLAMA_URL   = config.OLLAMA_BASE_URL
    _OLLAMA_MODEL = config.OLLAMA_MODEL
    _TEMP         = getattr(config, "OLLAMA_TEMPERATURE", 0.3)
    _MAXTOK       = getattr(config, "OLLAMA_MAX_TOKENS", 1024)
except Exception:                                   # אם מריצים מחוץ לשורש
    _OLLAMA_URL, _OLLAMA_MODEL, _TEMP, _MAXTOK = "http://localhost:11434", "qwen3:4b", 0.3, 1024

NEBIUS_BASE_URL = os.environ.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
NEBIUS_MODEL    = os.environ.get("NEBIUS_MODEL", "Qwen/Qwen3-235B-A22B")


# ─────────────────────────────────────────────
# Backends
# ─────────────────────────────────────────────
def _ollama_generate(messages, temperature, max_tokens):
    """מקומי / offline דרך Ollama."""
    import ollama
    client = ollama.Client(host=_OLLAMA_URL)
    resp = client.chat(
        model=_OLLAMA_MODEL,
        messages=messages,
        options={"temperature": temperature, "num_predict": max_tokens},
    )
    return resp["message"]["content"]


def _nebius_generate(messages, temperature, max_tokens):
    """ענן / תחרות דרך Nebius Token Factory (OpenAI-compatible)."""
    from openai import OpenAI            # lazy — נדרש רק ל-nebius
    key = os.environ.get("NEBIUS_API_KEY")
    if not key:
        raise RuntimeError("NEBIUS_API_KEY חסר — הגדר אותו או עבור ל-LLM_BACKEND=ollama")
    client = OpenAI(base_url=NEBIUS_BASE_URL, api_key=key)
    resp = client.chat.completions.create(
        model=NEBIUS_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content


_BACKENDS = {"ollama": _ollama_generate, "nebius": _nebius_generate}


# ─────────────────────────────────────────────
# API ציבורי
# ─────────────────────────────────────────────
def active_backend() -> str:
    return os.environ.get("LLM_BACKEND", "ollama").lower()


def generate(messages: list[dict], temperature: float | None = None,
             max_tokens: int | None = None) -> str:
    """
    מייצר תשובה מ-messages (פורמט OpenAI: [{role, content}, ...]).
    בוחר backend לפי LLM_BACKEND. מחזיר טקסט.
    """
    backend = active_backend()
    fn = _BACKENDS.get(backend)
    if fn is None:
        raise ValueError(f"LLM_BACKEND לא מוכר: {backend!r} (אפשרי: ollama | nebius)")
    return fn(messages,
             _TEMP if temperature is None else temperature,
             _MAXTOK if max_tokens is None else max_tokens)


if __name__ == "__main__":
    print("active backend:", active_backend())
    msgs = [{"role": "user", "content": "Reply with exactly: OK"}]
    print("response:", generate(msgs, max_tokens=10))
