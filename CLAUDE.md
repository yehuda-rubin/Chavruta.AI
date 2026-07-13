<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan:
`specs/001-chavruta-redesign/plan.md` (and its research.md, data-model.md,
contracts/, quickstart.md).

Active feature: **001-chavruta-redesign** — full redesign of Chavruta.AI as a
deployment-agnostic, dynamically-extensible RAG over the Jewish bookshelf.
Stack: Python 3.13 · bge-m3 embeddings · Qdrant (embedded local / server cloud) ·
hybrid retrieval (+optional rerank) · triple LLM backend selected by `CHAVRUTA_LLM_BACKEND`:
local DictaLM via Ollama · cloud Nebius Llama-3.3-70B · **bridge** (Claude answers grounded jobs
in-session, no external API — `src/chavruta/llm/bridge.py`) · FastAPI backend (`app/api.py`) +
SQLite chat history (`app/db.py`) + a **static offline UI** (`app/frontend/public/ui/chavruta.html`;
local Tailwind + self-hosted fonts; the React SPA in `app/frontend/src/` is deprecated). Hebrew RTL
+ English LTR i18n. Governed by `.specify/memory/constitution.md` (v1.1.0).

Load-bearing facts (see `docs/CORPUS.md §7`): the corpus stores base refs SPACE-form (`Genesis 1.1`)
and Talmud amud-linear (`Sanhedrin 45.1` = `N=2·daf∓1`) — the router emits DOTTED refs, so anchoring
canonicalises via `corpus/refs.py::with_ref_variants` or it silently misses. After loading the
collection, run `scripts/create_payload_indexes.py` (keyword index on ref/anchor_ref) or link
expansion / fetch_by_refs time out. Agentic retrieval: the model may reply `===NEED_SOURCES===` to
pull more sources (`src/chavruta/llm/agentic.py`).
<!-- SPECKIT END -->
