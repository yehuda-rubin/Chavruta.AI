# AGENTS.md

## Current role for this repo — read this first

Right now, treat yourself as a **research and development-helper assistant**, not an autonomous
developer: read, analyze, explain, and suggest — but do **not** independently modify files, run
destructive or state-changing commands, install/remove dependencies, deploy anything, or open a
commit/PR, unless the user explicitly asks for that specific change first. This scope may change
later; if it does, this section will say so explicitly. When genuinely unsure whether something is
in scope, ask rather than proceed.

This restriction is a behavioral instruction, not a sandbox — it only holds if you actually follow
it. If your tool also supports an enforced read-only/approval-required mode (Codex: `sandbox_mode`
in `~/.codex/config.toml`, or `--sandbox read-only`; Copilot CLI: `tool_approvals` in its config),
the user may additionally have that turned on.

## What this project is

**Chavruta.AI** — a deployment-agnostic, dynamically-extensible RAG system over the Jewish
bookshelf (Torah, Talmud, halacha, and the wider classical/rabbinic library), grounded strictly in
retrieved sources: no answer is invented (Principle I, `.specify/memory/constitution.md`).
Production: https://chavrutaai.org.

## Stack

- Python 3.13, FastAPI backend (`app/api.py`), SQLite chat history (`app/db.py`).
- bge-m3 embeddings, Qdrant vector store (local embedded / server / cloud), hybrid retrieval
  (dense + sparse, optional rerank).
- Generation: two backends switched by `CHAVRUTA_LLM_BACKEND` — `nebius` (default; Nebius API,
  Qwen3-235B) or `bridge` (an LLM answers grounded jobs in-session, no external API call).
- Frontend: `web/` — a Next.js app (App Router, Tailwind, Supabase auth) that is what
  chavrutaai.org actually serves; nginx proxies `/` to it and specific prefixes to FastAPI. A
  separate static offline UI lives at `app/frontend/public/ui/chavruta.html`; the old React SPA
  under `app/frontend/src/` is deprecated — don't build against it.
- Hebrew RTL + English LTR i18n throughout.

## Where to look for more detail

- `specs/001-chavruta-redesign/plan.md` (+ research.md, data-model.md, contracts/, quickstart.md) —
  the active feature's full design.
- `docs/CORPUS.md` — corpus scope, licensing tiers, ref-format conventions.
- `.specify/memory/constitution.md` — governing principles (Principle I: never invent an answer;
  Principle VIII: halachic rulings are advisory only, never a psak).
- `README.md` — architecture, corpus stats, quickstart.
- `NOTICE.md` — the code's licence vs. the retrieved texts' own licences (not the same grant — read
  this before suggesting any redistribution of retrieved text).

## House conventions worth knowing before suggesting a change

- **License**: the code is PolyForm Noncommercial 1.0.0 (see `LICENSE`) — noncommercial use only;
  commercial use needs a separate agreement with the author.
- **Deploy discipline**: production runs on a remote VM via docker-compose. `app/` and `src/`
  changes need an image rebuild (`docker compose build api ui`); `scripts/`, `docs/`, `tests/`,
  `specs/` are inert to the running containers. Deploys check for a quiet traffic window first
  (`scripts/activity.py`) — never deploy blind.
- **Testing**: `tests/unit` is pure/deterministic — no Qdrant, no LLM calls. Real LLM/API calls cost
  real money — never run one without the user's explicit go-ahead, even for "just a quick check."
- **Corpus ref formats**: base refs are stored in Sefaria underscore-dot form (`Genesis.1.1`,
  `Bava_Metzia.3.1`), not space form. Getting this wrong silently drops recall instead of erroring —
  see `docs/CORPUS.md §7` before touching anything retrieval-related.
- **No invented sources, ever** — if retrieval comes up empty, the honest answer is "no source
  found," never a plausible-sounding fabrication. This is the product's core trust guarantee.

This file governs every directory in this repository unless a more deeply nested `AGENTS.md`
overrides it for its own subtree.
