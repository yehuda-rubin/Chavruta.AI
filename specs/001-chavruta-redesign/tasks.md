---
description: "Task list for Chavruta.AI full redesign"
---

# Tasks: Chavruta.AI — Trustworthy Jewish-Text Study Partner (Full Redesign)

**Input**: Design documents from `specs/001-chavruta-redesign/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included where the Constitution mandates them — Principle V (measurable
trustworthiness → evaluation harness) and the interface contracts (conformance tests). They
are not exhaustive TDD; they target the grounding/trust guarantees.

**Total tasks**: 48 (T001–T043 plus inserted T015a, T016a, T024a, T033a, T036a).

**Organization**: Tasks are grouped by user story. **MVP = User Story 1.** User Stories 2–3
are incremental. **User Story 4 (halachic guidance) is DEFERRED** — out of this MVP until a
halachic corpus is added (per spec clarification); no tasks here.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1/US2/US3 for user-story phases; no label for Setup/Foundational/Polish
- All paths are relative to repo root `c:\Users\rubin\Documents\Chavruta.AI\`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and the new package skeleton

- [X] T001 Create the `src/chavruta/` package skeleton with `__init__.py` for each subpackage (`config`, `corpus`, `corpus/sources`, `embedding`, `store`, `retrieval`, `llm`, `generation`, `pipeline`, `intents`, `eval`) plus `app/`, `tests/{contract,integration,unit}/`, and an `eval/` data dir, per plan.md Project Structure
- [X] T002 Update `requirements.txt` with the redesign dependencies (FlagEmbedding/sentence-transformers for bge-m3, qdrant-client, openai client for Nebius, an Ollama client, streamlit, pytest) and pin versions compatible with Python 3.13
- [X] T003 [P] Configure tooling: `pyproject.toml`/`ruff`+formatter config and `pytest.ini` (test discovery for `tests/`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The deployment-agnostic core every user story depends on — config, data schema,
the four pluggable backends, corpus ingestion, hybrid retrieval, grounded generation, and the
base pipeline.

**⚠️ CRITICAL**: No user story can begin until this phase is complete.

### Config & schema

- [X] T004 Implement the `Profile`/settings object (env-driven `local`/`cloud` selection of every backend) in `src/chavruta/config/profile.py`
- [X] T005 [P] Define the core data types (`Work`, `Commentator`, `SourceText`, `Commentary` with `anchor_kind` source/commentary, `Chunk`, `Link`, `Citation`, `Query`, `Answer`) and the unified chunk schema in `src/chavruta/corpus/schema.py`, per data-model.md (incl. supercommentary anchor chains + the Link cross-reference entity)

### Backend interfaces (contracts → Protocols)

- [X] T006 [P] Define `EmbeddingBackend` Protocol (`embed_query`/`embed_batch`, dense+sparse) in `src/chavruta/embedding/base.py`, per contracts/embedding-backend.md
- [X] T007 [P] Define `VectorStore` Protocol (`ensure_collection`/`upsert`/`search`/`count`/`delete`, hybrid query + filters) in `src/chavruta/store/base.py`, per contracts/vector-store.md
- [X] T008 [P] Define `LLMBackend` Protocol (`generate`/`stream`, `GroundedPrompt`) in `src/chavruta/llm/base.py`, per contracts/llm-backend.md
- [X] T009 [P] Define `Retriever` Protocol (`retrieve` → `RetrievalResult` with `is_empty`) in `src/chavruta/retrieval/base.py`, per contracts/retriever.md

### Backend implementations

- [X] T010 Implement `BgeM3Embedding` (dense + learned sparse, CPU query / batch indexing) in `src/chavruta/embedding/bge_m3.py` (depends on T006)
- [X] T011 Implement `QdrantStore` (embedded path / server URL by config, named dense+sparse vectors, payload filters, idempotent upsert by `chunk_id`, delete-by-filter) in `src/chavruta/store/qdrant_store.py` (depends on T007)
- [X] T012 [P] Implement `LocalLLM` (Ollama serving DictaLM-2.0 Q4; model id from config; streaming) in `src/chavruta/llm/local.py` (depends on T008)
- [X] T013 [P] Implement `CloudLLM` (Nebius OpenAI-compatible client; model id from config; streaming) in `src/chavruta/llm/cloud.py` (depends on T008)

### Corpus (dynamic, extensible)

- [X] T014 Implement `CorpusRegistry` (register/list `Work`s, scope lookups) in `src/chavruta/corpus/registry.py` (depends on T005)
- [X] T015 Implement ingestion (fetch → normalize → chunk → schema) with a pluggable Sefaria source adapter in `src/chavruta/corpus/ingest.py` and `src/chavruta/corpus/sources/sefaria.py`, reusing existing fetch logic from `scripts/fetch_corpus.py`/`scripts/fetch_sefaria.py` (depends on T005, T014)
- [X] T015a Implement Links-graph + anchor-chain capture (ingest Sefaria Links into `Link` records; set `anchor_kind` on commentary chunks; support supercommentary anchors) in `src/chavruta/corpus/links.py` (depends on T005, T015)

### Retrieval & generation

- [X] T016 Implement `HybridRetriever` (bge-m3 dense+sparse → RRF fusion, dedup, pasuk-anchoring, per-commentator grouping, `work_id` scoping, commentator bias, relevance-threshold → `is_empty`) in `src/chavruta/retrieval/hybrid.py` (depends on T010, T011, T009)
- [X] T016a Implement the `LinkExpander` (follow `Link` edges + `anchor_ref` chains from anchor pesukim to supercommentaries and, across loaded corpora, the chain of transmission; merge with vector hits; respect `expand_depth` + work scoping) in `src/chavruta/retrieval/link_expand.py` (depends on T015a, T016), per contracts/retriever.md
- [X] T017 [P] Implement the optional `Reranker` (`bge-reranker-v2-m3`, config-gated on/off) in `src/chavruta/retrieval/rerank.py` (depends on T009)
- [X] T018 Implement the grounded prompt builder + **citation-enforcement gate** + honest "no grounded source" path in `src/chavruta/generation/grounded.py` (depends on T005) — this is the Principle I enforcement point
- [X] T019 Implement the base `ChavrutaPipeline` (build backends from `Profile`; `ask`/`ask_stream`; intent-routing skeleton; wire retrieve → generate → cite) in `src/chavruta/pipeline/pipeline.py` (depends on T016, T012/T013, T018)

### Load data + verify the contracts

- [X] T020 Implement `scripts/load_to_store.py` to load the existing embedded Tanakh vectors into the configured store (no re-embedding) (depends on T011, T014)
- [X] T021 [P] Contract conformance test for `EmbeddingBackend` (dense length == dim; determinism; HE/EN parity) in `tests/contract/test_embedding.py` (depends on T010)
- [X] T022 [P] Contract conformance test for `VectorStore` (idempotent upsert; filter isolation; hybrid ≥ dense-only; embedded/server parity) in `tests/contract/test_vector_store.py` (depends on T011)
- [X] T023 [P] Contract conformance test for `LLMBackend` (answers in question language; local/cloud interchangeable) in `tests/contract/test_llm.py` (depends on T012, T013)
- [X] T024 [P] Contract conformance test for `Retriever` (named-commentator surfacing; out-of-corpus → `is_empty`; scoping) in `tests/contract/test_retriever.py` (depends on T016)
- [X] T024a [P] Extensibility test for **SC-005** — register a small dummy `Work` via `CorpusRegistry`, ingest + index it, and assert it is retrievable with **no change** to retrieval/ranking/generation code (data/config-only growth, Principle III) in `tests/integration/test_extensibility.py` (depends on T014, T016)

**Checkpoint**: Foundation ready — the deployment-agnostic core works; user stories can begin.

---

## Phase 3: User Story 1 - Grounded answer with citations (Priority: P1) 🎯 MVP

**Goal**: Ask a Tanakh question (HE/EN) and get an answer built only from retrieved sources,
every claim cited, with an honest "no source found" when nothing relevant exists.

**Independent Test**: Run the eval set + the quickstart scenarios 1–3; verify cited answers
resolve to real sources, bilingual parity holds, and out-of-corpus questions never fabricate.

### Implementation

- [ ] T025 [US1] Implement intent + language detection and named-ref/commentator extraction (default intent `qa`) in `src/chavruta/intents/router.py`
- [ ] T026 [US1] Wire the `qa` path end-to-end in `ChavrutaPipeline.ask` (grounded answer, `citations`, `grounded`/`no_source`) in `src/chavruta/pipeline/pipeline.py` (depends on T019, T025)
- [ ] T027 [P] [US1] Implement the one-shot CLI `scripts/ask.py` (`--intent`, `--profile`, prints answer + citations)
- [ ] T028 [US1] Implement the Streamlit chat `app/streamlit_app.py` (RTL/LTR rendering, clickable citations, in-session conversation context, streaming responses) (depends on T026)
- [ ] T029 [P] [US1] Implement the evaluation harness (retrieval@K + grounding scoring, reproducible/comparable report, runs per profile) in `src/chavruta/eval/harness.py` and `scripts/run_eval.py`
- [ ] T030 [P] [US1] Author the evaluation dataset `eval/tanakh_v1.jsonl` — 100+ Tanakh questions (HE/EN) with `expected_refs` and grounding checks, per data-model.md EvaluationItem
- [ ] T031 [P] [US1] Integration tests for the qa path (grounded happy path, honest no-source, HE/EN parity, **and that the answer quotes the Hebrew source text per FR-012**) in `tests/integration/test_qa.py`

**Checkpoint**: MVP — grounded, cited, bilingual Q&A over Tanakh, measured by the eval set.
**STOP and VALIDATE** before proceeding.

---

## Phase 4: User Story 2 - Explain & compare commentators (Priority: P2)

**Goal**: Explain a single commentator's view on a verse, or compare several, with correct
attribution and surfaced disagreements — all grounded and cited.

**Independent Test**: Quickstart scenario 4 + integration tests: one-commentator explanation,
two-commentator comparison, and a commentator who has no comment on the verse.

### Implementation

- [ ] T032 [US2] Add the `explain`/`compare` intent to `src/chavruta/intents/router.py` (single vs multi-commentator, target verse resolution)
- [ ] T033 [US2] Implement the explanation + comparison generation (per-commentator grounding, attribution, disagreement surfacing, "no comment here" handling) in `src/chavruta/generation/grounded.py` and wired in `src/chavruta/pipeline/pipeline.py` (depends on T032, T026)
- [ ] T033a [US2] Enable supercommentary surfacing in the compare path — when comparing two commentators, use `expand_links` to bring sources whose anchor is one of those commentators' comments (who *explains the dispute*), attributed and cited, in `src/chavruta/intents/router.py` + `src/chavruta/pipeline/pipeline.py` (depends on T016a, T033). *(Surfaces supercommentaries once such works are loaded.)*
- [ ] T034 [P] [US2] Integration tests (explain one commentator; compare two with disagreement; missing-commentator case; supercommentary-on-dispute when available) in `tests/integration/test_explain.py`

**Checkpoint**: US1 and US2 both work independently.

---

## Phase 5: User Story 3 - Prepare a structured lesson (Priority: P3)

**Goal**: Produce a structured shiur on a topic/parasha — sources, structure, discussion
points — every cited source resolving.

**Independent Test**: Quickstart scenario 5 + integration test: a lesson request returns a
coherent structure whose every citation resolves.

### Implementation

- [ ] T035 [P] [US3] Add the `LessonPlan` type (topic/parasha, sections with source_refs + explanation + discussion_points + citations) to `src/chavruta/corpus/schema.py`
- [ ] T036 [US3] Add the `lesson` intent + structured-lesson builder (select sources, build sections, discussion points, attach resolving citations) in `src/chavruta/intents/router.py`, `src/chavruta/generation/grounded.py`, and `src/chavruta/pipeline/pipeline.py` (depends on T026, T035)
- [ ] T036a [US3] Make the lesson builder **multi-corpus chain-aware** — use `expand_links` to follow the chain of transmission (pasuk → Rishonim → Acharonim → Halacha) across all loaded corpora, ordering sections along the chain with citations at each step (depends on T016a, T036). *(Spans pesukim + commentators in the Tanakh MVP; full chain activates as corpora are loaded.)*
- [ ] T037 [P] [US3] Integration test (lesson on a topic → structured sections with resolving citations) in `tests/integration/test_lesson.py`

**Checkpoint**: All MVP user stories (1–3) independently functional over Tanakh.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Hardening, parity, performance, and migration off the legacy flat modules.

- [ ] T038 [P] Profile-parity integration test (same request on `local` and `cloud` cites the same sources) in `tests/integration/test_parity.py` (SC-006)
- [ ] T039 Tune retrieval on the target laptop and decide the local reranker on/off default empirically via the eval harness; record the outcome in `specs/001-chavruta-redesign/research.md` (D5/D7 open item)
- [ ] T040 [P] Unit tests for RRF fusion, dedup/anchoring, and the citation-enforcement gate in `tests/unit/`
- [ ] T041 [P] Migrate and remove the legacy flat modules (`src/rag_pipeline.py`, `src/vector_store.py`, `src/llm_backend.py`, `src/sefaria_client.py`) once superseded by `src/chavruta/`
- [ ] T042 [P] Update docs to the new architecture (`README.md`, `docs/architecture.md`, `docs/DECISIONS.md`) referencing the plan
- [ ] T043 Run the full `quickstart.md` validation end-to-end on the offline profile and confirm all scenarios pass

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: no dependencies — start immediately.
- **Foundational (Phase 2)**: depends on Setup — **BLOCKS all user stories**.
- **User Stories (Phase 3–5)**: all depend on Foundational. US1 first (MVP). US2/US3 can then
  proceed in parallel or in priority order; each is independently testable.
- **Polish (Phase 6)**: depends on the desired user stories being complete.

### Key intra-phase dependencies

- Interfaces (T006–T009) before their implementations (T010–T013, T016–T017).
- Schema (T005) before corpus (T014–T015), generation (T018), and pipeline (T019).
- Retriever + LLM + generation (T016, T012/T013, T018) before the base pipeline (T019).
- Base pipeline (T019) + router (T025) before the qa wiring (T026); T026 before the UI (T028).
- `LessonPlan` (T035) before the lesson builder (T036).

### Parallel opportunities

- Setup: T003 ∥ others.
- Foundational interfaces: T005, T006, T007, T008, T009 all ∥ (different files).
- Foundational impls: T012 ∥ T013 (LLMs); T017 ∥ T016-track; contract tests T021–T024 all ∥
  (after their impls).
- US1: T027, T029, T030, T031 ∥ (CLI, harness, dataset, tests are different files).
- US2/US3 can be built by different developers in parallel after the MVP.

---

## Parallel Example: Foundational interfaces

```text
# Define all four backend Protocols + schema together (different files):
Task T005: core schema in src/chavruta/corpus/schema.py
Task T006: EmbeddingBackend Protocol in src/chavruta/embedding/base.py
Task T007: VectorStore Protocol in src/chavruta/store/base.py
Task T008: LLMBackend Protocol in src/chavruta/llm/base.py
Task T009: Retriever Protocol in src/chavruta/retrieval/base.py
```

## Parallel Example: User Story 1 delivery

```text
# After the qa path (T026) is wired, run these in parallel (different files):
Task T027: CLI scripts/ask.py
Task T029: eval harness src/chavruta/eval/harness.py
Task T030: eval dataset eval/tanakh_v1.jsonl
Task T031: integration tests tests/integration/test_qa.py
```

---

## Implementation Strategy

### MVP first (User Story 1 only)

1. Phase 1 Setup → 2. Phase 2 Foundational (critical, blocks all) → 3. Phase 3 US1 →
4. **STOP and VALIDATE** against the eval set + quickstart scenarios 1–3 → 5. Demo offline.

### Incremental delivery

Foundation → US1 (MVP, grounded Q&A) → US2 (explain/compare) → US3 (lesson prep). Each story
adds value without breaking the previous ones. US4 (halacha) is added later together with a
halachic corpus.

---

## Notes

- [P] = different files, no incomplete dependencies. [US#] maps a task to its user story.
- The redesign **reuses** the existing fetched corpus and embeddings — no re-embedding needed
  to stand up the MVP (T020 loads existing vectors).
- **Cross-corpus content is data, not code**: supercommentaries (Mizrachi, Gur Aryeh, Sifsei
  Chachamim) and halachic works (Shulchan Aruch, Tur, Mishneh Torah) are added later via the
  CorpusRegistry. The schema (`anchor_kind`, `Link`), the `LinkExpander` (T016a), and the
  chain-aware lesson/compare paths (T033a, T036a) are built in the MVP so that loading those
  works activates the full Torah→Halacha chain and supercommentary-on-dispute **with no code
  change** (Principle III); the extensibility test T024a guards this (SC-005).
- Principle I (grounding) is enforced concretely at T018 (citation gate) and validated at
  T021–T024, T031, and the eval harness (T029/T030).
- Principle II (deployment-agnostic) is validated by the parity tests (T022, T023, T038).
- Commit after each task or logical group; stop at any checkpoint to validate independently.
