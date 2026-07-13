<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan:
`specs/001-chavruta-redesign/plan.md` (and its research.md, data-model.md,
contracts/, quickstart.md).

Active feature: **001-chavruta-redesign** — full redesign of Chavruta.AI as a
deployment-agnostic, dynamically-extensible RAG over the Jewish bookshelf.
Stack: Python 3.13 · bge-m3 embeddings · Qdrant (embedded local / server cloud) ·
hybrid retrieval (+optional rerank) · triple LLM backend selected by `CHAVRUTA_LLM_BACKEND`:
local DictaLM via Ollama · **Nebius `Qwen/Qwen3-235B-A22B-Instruct-2507`** · **bridge** (Claude answers
grounded jobs in-session, no external API — `src/chavruta/llm/bridge.py`). **Default runtime (incl.
locally) uses the Nebius API for generation** — `scripts/serve.ps1`: local CPU embedding + local Qdrant
server + `CHAVRUTA_LLM_BACKEND=nebius` (key read from `.env`). Bridge (`scripts/serve_bridge.ps1`) and
local DictaLM remain available but are no longer the default (the earlier no-API rule was lifted).
FastAPI backend (`app/api.py`) + SQLite chat history (`app/db.py`) + a **static offline UI**
(`app/frontend/public/ui/chavruta.html`; local Tailwind + self-hosted fonts; the React SPA in
`app/frontend/src/` is deprecated). Hebrew RTL + English LTR i18n. Governed by
`.specify/memory/constitution.md` (v1.1.0).

Corpus: **15 tiers** in the live `chavruta` collection (2.93M points), incl. **`talmud_yerushalmi`**
(added 2026-07-13 via `fetch_full_dynamic.py --domain yerushalmi` → Lightning embed → `bootstrap_rag.py
--append`). See [[loaded-collection-tiers]] / `docs/CORPUS.md §5`.

Load-bearing facts (see `docs/CORPUS.md §7`): the corpus stores base refs SPACE-form (`Genesis 1.1`)
and Talmud amud-linear (`Sanhedrin 45.1` = `N=2·daf∓1`) — the router emits DOTTED refs, so anchoring
canonicalises via `corpus/refs.py::with_ref_variants` or it silently misses. After loading, run
`scripts/create_payload_indexes.py` (keyword index on ref/anchor_ref) or link expansion / fetch_by_refs
time out. Use `CHAVRUTA_QUERY_PLANNER=heuristic` (the LLM planner hallucinates named_refs that scope
retrieval to the wrong tractate → 0 sources); a wrong scope now falls back to unscoped semantic search
(`hybrid.retrieve`). Agentic retrieval: the model may reply `===NEED_SOURCES===` to pull more sources,
and the FINAL round forces a written answer instead of degrading (`src/chavruta/llm/agentic.py`). The
lesson source-sheet is assembled from the FULL retrieved texts (not the model's truncated echo); a
Hebrew-only rule + `_strip_foreign` scrub the model's CJK/Cyrillic multilingual bleed (`app/api.py`).
<!-- SPECKIT END -->
