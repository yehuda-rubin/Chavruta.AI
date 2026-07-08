<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan:
`specs/001-chavruta-redesign/plan.md` (and its research.md, data-model.md,
contracts/, quickstart.md).

Active feature: **001-chavruta-redesign** — full redesign of Chavruta.AI as a
deployment-agnostic, dynamically-extensible RAG over the Jewish bookshelf.
Stack: Python 3.13 · bge-m3 embeddings · Qdrant (embedded local / server cloud) ·
hybrid retrieval (+optional rerank) · dual LLM (local DictaLM via Ollama / cloud Nebius
Llama-3.3-70B) · FastAPI backend (`app/api.py`) + SQLite chat history (`app/db.py`) +
React/Vite SPA (`app/frontend/`, Hebrew RTL + English LTR i18n). Governed by
`.specify/memory/constitution.md` (v1.1.0).
<!-- SPECKIT END -->
