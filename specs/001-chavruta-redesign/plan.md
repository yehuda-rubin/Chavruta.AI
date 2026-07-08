# Implementation Plan: Chavruta.AI — Trustworthy Jewish-Text Study Partner (Full Redesign)

**Branch**: `001-chavruta-redesign` | **Date**: 2026-06-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-chavruta-redesign/spec.md`

> **Implementation note (2026-06-29):** this document is the original design record. Two things
> diverged in implementation and are intentionally **not** rewritten inline below: (1) the UI
> shipped as a **React + Vite SPA over a FastAPI backend with SQLite chat history**
> (`app/api.py`, `app/db.py`, `app/frontend/`), **not** Streamlit; (2) the corpus expanded from
> the Tanakh MVP to the **full Sefaria bookshelf** served from a hybrid Qdrant index. For the
> living description of the system see the root [README.md](../../README.md) and
> [docs/CORPUS.md](../../docs/CORPUS.md); for how to run/validate it see
> [quickstart.md](./quickstart.md). References to "Streamlit" below are historical.

## Summary

Rebuild Chavruta.AI as a **deployment-agnostic, dynamically-extensible RAG system** that
answers questions over the Jewish bookshelf with grounded, cited answers. The MVP goes deep
on **Tanakh** and delivers three capabilities — grounded Q&A, explain/compare commentators,
and lesson preparation (halachic guidance is deferred until a halachic corpus is added).

**Technical approach**: A thin, custom Python pipeline composed of **pluggable backends**
selected purely by configuration (Constitution Principle II):

- **Embedding**: `bge-m3` (multilingual HE/EN, dense + sparse) — same model both profiles.
- **Vector store**: **Qdrant** — embedded locally, server in the cloud.
- **Retrieval**: **dual** — (a) **hybrid vector** (dense + lexical sparse from bge-m3, fused
  via RRF) with **optional reranking** (heavy cross-encoder in cloud, optional/off on laptop),
  plus pasuk-anchored, per-commentator grouping; and (b) **link-based expansion** that follows
  Sefaria's Links graph and `anchor_ref` chains (incl. supercommentary) to gather related
  material and traverse the chain of transmission across corpora (pasuk → Rishonim →
  Acharonim → Halacha).
- **Generation (LLM)**: **dual-model by profile** — LOCAL uses a small Hebrew-capable model
  that fits ~4–5GB RAM (`DictaLM-2.0-Instruct`, GGUF Q4, via Ollama/llama.cpp); CLOUD uses a
  stronger serverless model (Nebius Token Factory, OpenAI-compatible). Same prompt + same
  grounding/citation enforcement in both.
- **Corpus**: a **corpus registry** so adding a work/commentator (including supercommentaries
  and halachic works) is a data/config operation; ingestion also captures the **Links graph**
  and **anchor chains** (`anchor_kind=source|commentary`).
- **UI**: Streamlit chat now (in-session context), designed to allow a structured study UI
  later without re-architecting the core.
- **Trust**: an automated **evaluation harness** over a 100+ Tanakh question set.

## Technical Context

**Language/Version**: Python 3.13 (existing project `.venv`).

**Primary Dependencies**:
- Embedding: `FlagEmbedding`/`sentence-transformers` running `BAAI/bge-m3` (dense + sparse).
- Vector store: `qdrant-client` (embedded mode local; server mode cloud).
- Local LLM: Ollama (or llama.cpp) serving `DictaLM-2.0-Instruct` GGUF Q4 (~4.4GB).
- Cloud LLM: OpenAI-compatible client pointed at Nebius Token Factory.
- Optional reranker: `bge-reranker-v2-m3` (cloud profile / optional local).
- UI: Streamlit. Orchestration: thin custom Python (no heavy LLM framework — Principle VI).

**Storage**:
- Vectors in **Qdrant** (embedded `.qdrant` path local / Qdrant server cloud).
- Corpus chunks as portable JSON/Parquet on disk; embeddings as portable `.npy` so the
  vector backend can be swapped without re-embedding (Principle II / reproducibility).
- No external DB required for the offline profile; conversation state is in-memory
  (in-session only — per clarification).

**Testing**: `pytest` for unit/contract/integration; the **evaluation harness** (`eval/`)
for grounding/retrieval quality gates (Principle V).

**Target Platform**: Desktop (Windows/macOS/Linux) for the offline profile; Linux cloud for
the product profile. Same codebase.

**Project Type**: Single Python project exposing a library + CLI + Streamlit app (with a
clean seam for a future web API).

**Performance Goals**:
- Offline: interactive cited answer within a few seconds on a CPU-only 16GB laptop;
  retrieval (embed query + search + rank) target ~1s; generation is the dominant cost.
- Cloud: per-token serverless generation; scales horizontally.

**Constraints**:
- **Offline-capable**, no network at query time in the local profile.
- Local LLM must fit **~4–5GB RAM** (DictaLM-2.0 Q4); total working set comfortably under
  16GB alongside bge-m3 + Qdrant.
- **Deployment-agnostic**: local vs cloud differ by **configuration only**, no forked code.
- **Grounding is mandatory**: answers built only from retrieved sources, every claim cited.

**Scale/Scope**:
- MVP corpus: all Tanakh + ~12 commentators (~127k chunks, already fetched).
- Designed to grow to **millions** of chunks across many works (Gemara, Halacha, Emunah…)
  via the corpus registry without architectural change.

## Index build & distribution (Job-as-factory / HF-as-warehouse)

Computing the index is separated from distributing it, so the expensive GPU work happens
**once** and everyone else just downloads. This keeps the offline profile genuinely
zero-cost (no Qdrant Cloud, no GPU) while still satisfying the Nebius challenge's Job +
Endpoint deliverables.

- **The Job is the factory** (`scripts/ingest_job.py`, Nebius Serverless GPU Job). It:
  1. gets the raw corpus — reuse a local file, else download a **Hugging Face corpus
     dataset**, else fall back to a live Sefaria fetch (used only to (re)build from source);
  2. embeds it with bge-m3 (dense + sparse) on the GPU → portable `out/` artifact
     (`corpus_vectors.npy` + `corpus_sparse.jsonl` + `corpus_meta.jsonl`);
  3. **publishes** that prebuilt index to a **Hugging Face dataset** (the downloadable
     artifact);
  4. *optionally* upserts into **Qdrant Cloud** so the live **Endpoint** has data.
- **Hugging Face is the warehouse.** A Serverless Job's filesystem is ephemeral and a user's
  machine has no public address for the cloud to push to, so the Job cannot deliver to a
  laptop directly. HF is the shared mailbox: the Job **pushes**, clients **pull**.
- **The user just downloads** (`scripts/bootstrap_rag.py`): one command pulls the prebuilt
  index from HF and loads it into a local Qdrant (embedded or server, per `Profile`) — no
  GPU, no re-embedding. The same `load_processed_chunks` reuse path feeds both the local
  load and the cloud load, so local and cloud stay byte-identical (Principle II).
- **Who runs the Job:** the maintainer (initial build + every corpus update — Tanakh,
  Mishnah, Gemara…), and anyone embedding **their own** corpus (Principle III). Regular
  users never run it.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | How the plan satisfies it | Status |
|---|-----------|---------------------------|--------|
| I | Grounded, Never Invented (NON-NEGOTIABLE) | Generation prompt is built only from retrieved sources; a citation-enforcement step validates every claim maps to a retrieved source; explicit "no grounded source found" path; eval measures grounding. | ✅ Pass |
| II | Deployment-Agnostic Core | All four backends (Embedding/VectorStore/LLM/Reranker) sit behind interfaces selected by a `Profile` config; no forked code paths; portable vector artifacts. | ✅ Pass |
| III | Dynamic, Extensible Corpus | A `CorpusRegistry` + uniform chunk schema; adding a work/commentator is data/config; ingestion supports incremental add + re-index without full rebuild. | ✅ Pass |
| IV | Bilingual by Design | bge-m3 (HE/EN) retrieval; Hebrew-capable LLM (DictaLM); answer-in-question-language prompt; RTL-aware UI; every chunk stores HE (+EN). | ✅ Pass |
| V | Measurable Trustworthiness | `eval/` harness over a 100+ item set; grounding/retrieval scores reproducible and comparable across runs; gate before accepting changes. | ✅ Pass |
| VI | Simplicity First (YAGNI) | Thin custom orchestration instead of a heavy framework; reuse proven bge-m3 + Qdrant; reranking optional; one project. | ✅ Pass |
| VII | User Experience | Streamlit chat with clickable citations, in-session follow-ups, honest empty/error states, RTL/LTR rendering, responsive feedback. | ✅ Pass |
| VIII | Halachic Humility & Deference | P4 deferred for MVP (no halachic corpus yet); the intent/router and prompt design reserve a halachic path that will always carry the "not a substitute for a rav" caveat. | ✅ Pass (N/A in MVP, not precluded) |

**Result**: All gates pass. No violations → Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-chavruta-redesign/
├── plan.md              # This file
├── research.md          # Phase 0 output — key technical decisions + rationale
├── data-model.md        # Phase 1 output — entities, chunk schema, relationships
├── quickstart.md        # Phase 1 output — run the offline profile + eval end-to-end
├── contracts/           # Phase 1 output — pluggable backend + pipeline interface contracts
│   ├── embedding-backend.md
│   ├── vector-store.md
│   ├── llm-backend.md
│   ├── retriever.md
│   └── pipeline-query.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

Refactors the current flat `src/` into a cohesive package with clear seams. The redesign
introduces interfaces and a corpus registry; existing modules (`rag_pipeline.py`,
`vector_store.py`, `llm_backend.py`, `sefaria_client.py`) are decomposed into these homes.

```text
src/chavruta/
├── config/            # Profile + settings (local vs cloud), env-driven selection
├── corpus/            # CorpusRegistry, chunk schema, ingestion (fetch→normalize→chunk),
│   │                  #   Links graph + anchor-chain capture
│   ├── sources/       # per-source adapters (Sefaria today; pluggable for new works)
│   └── links.py       # Link ingestion + the cross-reference / anchor-chain graph
├── embedding/         # EmbeddingBackend interface + BgeM3Embedding impl
├── store/             # VectorStore interface + QdrantStore impl (embedded/server)
├── retrieval/         # HybridRetriever (dense+sparse+RRF) + LinkExpander, optional Reranker,
│                      #   ranking/dedup/anchoring
├── llm/               # LLMBackend interface + LocalLLM (Ollama/DictaLM) + CloudLLM (Nebius)
├── generation/        # grounded prompt builder + citation enforcement + "no source" path
├── pipeline/          # orchestration: query → retrieve → rank → generate → cite
├── intents/           # capability routing: qa | explain | lesson  (halacha reserved)
└── eval/              # evaluation harness + datasets + scoring

app/
└── streamlit_app.py   # chat UI (RTL-aware, clickable citations, in-session context)

scripts/               # fetch_corpus, embed_corpus_gpu, load_to_store, ask (CLI), run_eval
#                        ingest_job (Nebius GPU factory: build+publish), bootstrap_rag (user download)
tests/
├── contract/          # backend interface conformance tests
├── integration/       # end-to-end pipeline + profile-parity tests
└── unit/
```

**Structure Decision**: Single Python project organized as the `src/chavruta/` package above.
The package boundaries mirror the pluggable-backend interfaces (Principle II) and the
corpus registry (Principle III). The Streamlit app and CLI are thin entry points over the
same `pipeline/`. This keeps one deployable codebase whose behavior changes by config, and
isolates each concern so a new corpus or a new backend is an additive change.

## Complexity Tracking

> No Constitution Check violations. No entries required.
