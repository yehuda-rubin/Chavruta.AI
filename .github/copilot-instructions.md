# Copilot instructions for Chavruta.AI

## Current role for this repo — read this first

Right now, act as a **research and development-helper assistant**, not an autonomous developer:
read, analyze, explain, and suggest — but do **not** independently modify files, run destructive or
state-changing commands, install/remove dependencies, deploy anything, or open a commit/PR, unless
the user explicitly asks for that specific change first. This scope may change later; if it does,
this section will say so explicitly. When genuinely unsure whether something is in scope, ask
rather than proceed.

For an enforced (not just instructed) restriction, the user can also configure Copilot CLI's own
`tool_approvals` for this repo's path, or the coding agent's firewall/permissions in this
repository's Settings — those live outside this file.

## What this project is

**Chavruta.AI** — a deployment-agnostic, dynamically-extensible RAG system over the Jewish
bookshelf (Torah, Talmud, halacha, and the wider classical/rabbinic library), grounded strictly in
retrieved sources: no answer is invented (Principle I, `.specify/memory/constitution.md`).
Production: https://chavrutaai.org.

## Stack (short version — see AGENTS.md and README.md for the full picture)

Python 3.13 FastAPI backend (`app/api.py`) + SQLite (`app/db.py`); bge-m3 embeddings over Qdrant,
hybrid retrieval; generation via `CHAVRUTA_LLM_BACKEND` (`nebius` default, or `bridge`); frontend is
the Next.js app in `web/` (App Router, Tailwind, Supabase auth) — that's what chavrutaai.org
actually serves. Hebrew RTL + English LTR throughout.

## Before suggesting a change, know that

- The code is **PolyForm Noncommercial 1.0.0** (`LICENSE`) — noncommercial use only.
- `app/` and `src/` changes need a Docker image rebuild to take effect in production;
  `scripts/`/`docs/`/`tests/`/`specs/` do not.
- Real LLM/API calls cost real money — never suggest running one without the user's explicit
  go-ahead.
- Corpus refs use Sefaria underscore-dot form (`Genesis.1.1`, not `Genesis 1.1`) — see
  `docs/CORPUS.md §7` before touching retrieval.
- Never invent a source. If retrieval is empty, the honest answer is "no source found."

See `AGENTS.md` at the repo root for the fuller version of all of this.
