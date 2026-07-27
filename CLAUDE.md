<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan:
`specs/001-chavruta-redesign/plan.md` (and its research.md, data-model.md,
contracts/, quickstart.md).

Active feature: **001-chavruta-redesign** — full redesign of Chavruta.AI as a
deployment-agnostic, dynamically-extensible RAG over the Jewish bookshelf.
Stack: Python 3.13 · bge-m3 embeddings · Qdrant (embedded local / server cloud) ·
hybrid retrieval (+optional rerank) · **two** LLM backends selected by `CHAVRUTA_LLM_BACKEND`:
**`nebius` — the API (`Qwen/Qwen3-235B-A22B-Instruct-2507`), DEFAULT** · **`bridge`** (Claude answers
grounded jobs in-session, no external API — `src/chavruta/llm/bridge.py`). The local DictaLM/Ollama
backend was **removed** (product decision 2026-07-13). **Default runtime (incl. locally) uses the
Nebius API for generation** — `scripts/serve.ps1`: local CPU embedding + local Qdrant server +
`CHAVRUTA_LLM_BACKEND=nebius` (key from `.env`); bridge (`scripts/serve_bridge.ps1`) for the no-API path.
FastAPI backend (`app/api.py`) + SQLite chat history (`app/db.py`) + a **static offline UI**
(`app/frontend/public/ui/chavruta.html`; local Tailwind + self-hosted fonts; the React SPA in
`app/frontend/src/` is deprecated). Hebrew RTL + English LTR i18n. Governed by
`.specify/memory/constitution.md` (v1.1.0).

Corpus: the live production collection is **`chavruta_commercial`** (**2,403,599 points**, **15 tiers**,
**100% commercially-licensed** — PD/CC0/CC-BY/CC-BY-SA only, fail-closed `rights.allows_commercial_use`),
served **on-disk** (`CHAVRUTA_MEM_TIER=ssd`: HNSW + dense + sparse + payload all memmapped, ~1–2 GB RAM).
It **REPLACED** the old mixed-licence `chavruta` collection on **2026-07-20** — `serve.ps1` + `.env` now
point at it. Built on a cloud H100 (merge 15 tiers → bge-m3 embed → index → snapshot) and restored
locally from the snapshot on HF (`Yehuda-Rubin/chavruta-commercial-index`) via
`scripts/restore_commercial_tonight.ps1` (local-file `snapshots/recover`, RAM-safe — the HTTP upload
path OOMs a 16 GB machine). See [[commercial-corpus-on-hf]] / [[loaded-collection-tiers]] / `docs/CORPUS.md §5`.
Verified end-to-end via the bridge (Claude in-session): explain/compare/halacha/lesson all grounded with
correct citations, the agentic `===NEED_SOURCES===` loop fires on thin retrieval, and out-of-corpus
questions return `no_source` (Principle I) — no invention. Known follow-up: per-chunk payload `license`
field is EMPTY and its indexes use the wrong names (`license_he`/`license_en` vs the actual `license`) —
harmless (the whole collection is already commercial) unless per-chunk CC-BY attribution is wanted later.

Load-bearing facts (see `docs/CORPUS.md §7`): the **commercial** corpus stores base refs in **Sefaria
underscore-dot form** — `Genesis.1.1`, `Exodus.20.1`, `Bava_Metzia.3.1` (underscore for the book's
spaces!), `Mishnah_Sukkah.3.5` — NOT the old `chavruta` space-form (`Genesis 1.1`, `Bava Metzia 3.1`);
Talmud is amud-linear (`Bava Metzia 2a` → corpus `Bava_Metzia.3.1`, `N=2·daf∓1`). The router emits
DOTTED refs, so anchoring MUST emit BOTH spellings via `corpus/refs.py::with_ref_variants` (`_to_sefaria_ref`
adds the underscore-dot variant + chapter→opening-verse) or the base pasuk/daf silently never anchors
(this was a real recall bug — retrieval@8 was ~50% until fixed 2026-07-24, now ~83%; see [[ref-format-anchoring]]).
After loading, run
`scripts/create_payload_indexes.py` (keyword index on ref/anchor_ref) or link expansion / fetch_by_refs
time out. Use `CHAVRUTA_QUERY_PLANNER=heuristic` (the LLM planner hallucinates named_refs that scope
retrieval to the wrong tractate → 0 sources); a wrong scope now falls back to unscoped semantic search
(`hybrid.retrieve`). Agentic retrieval: the model may reply `===NEED_SOURCES===` to pull more sources,
and the FINAL round forces a written answer instead of degrading (`src/chavruta/llm/agentic.py`). The
lesson source-sheet is assembled from the FULL retrieved texts (not the model's truncated echo); a
Hebrew-only rule + `_strip_foreign` scrub the model's CJK/Cyrillic multilingual bleed (`app/api.py`).

**External DEV models (Devin CLI, Novita) — read `docs/DEV_MODELS.local.md` before using any of them.**
It holds the API keys, the exact model slugs, which model to hand which kind of task, and the traps
already hit (Devin Free serves ONLY its default model; Macaron burns its whole budget on Chinese
`reasoning_content` unless given a large `max_tokens`, and 503s under load). That file is **gitignored
because it contains secrets** — it is not on GitHub and must never be committed. These are tooling for
building the product; the product's own engine is still `CHAVRUTA_LLM_BACKEND` (`nebius` / `bridge`).
<!-- SPECKIT END -->
