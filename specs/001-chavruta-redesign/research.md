# Phase 0 Research: Chavruta.AI Redesign

Key technical decisions, each with rationale and the alternatives considered. All choices
are constrained by the Constitution (esp. II deployment-agnostic, III dynamic corpus, VI
simplicity) and the offline envelope (CPU-only 16GB laptop).

## D1 — Local LLM: DictaLM-2.0-Instruct (GGUF Q4), config-swappable

- **Decision**: Use `DictaLM-2.0-Instruct` (7B, Mistral-based, Hebrew-specialized by Dicta)
  quantized to GGUF **Q4_K_M (~4.4GB)** as the default LOCAL generation model, served via
  Ollama/llama.cpp. The model id is a **config value**, so it can be swapped (e.g. Q3 ~3.5GB
  if RAM is tight, or a 3B multilingual model) without code changes.
- **Rationale**: The system is Hebrew-first (Principle IV) and must produce quality Hebrew
  reasoning over quoted sources. A Hebrew-specialized model beats a general multilingual one
  at this. Q4 fits the user's stated ~4–5GB RAM budget and leaves headroom under 16GB
  alongside bge-m3 (~2GB) and Qdrant.
- **Alternatives considered**:
  - *Qwen2.5-3B/7B multilingual* — lighter/faster, decent Hebrew, but not Hebrew-specialized;
    kept as a config-selectable fallback.
  - *granite4.1:3b (current)* — RAG-native but weaker Hebrew; superseded as default.
  - *Cloud-only generation* — rejected: violates the fully-offline requirement (FR-017).

## D2 — Cloud LLM: stronger serverless model via Nebius (OpenAI-compatible)

- **Decision**: CLOUD profile generates via Nebius Token Factory (OpenAI-compatible API)
  using a stronger model, selected by config. Same prompt, same grounding/citation rules.
- **Rationale**: Per the user's dual-model strategy and Principle II — better quality and
  scale where compute is available, with identical pipeline behavior.
- **Alternatives considered**: self-hosted GPU serving (heavier ops, deferred); a single
  model for both profiles (rejected — can't satisfy both the laptop and product quality).

## D3 — Embedding: keep bge-m3 (dense + sparse), shared by both profiles

- **Decision**: Keep `BAAI/bge-m3` (1024-dim dense + learned sparse), same model in both
  profiles; query-time embedding on CPU locally, bulk/GPU embedding for indexing.
- **Rationale**: Proven in this project, multilingual so HE and EN questions land near the
  same source (FR-011), and it natively emits **both dense and sparse** vectors — which
  directly enables hybrid retrieval (D5) without a second model.
- **Alternatives considered**: E5-multilingual, multilingual-MiniLM (weaker on HE);
  Hebrew-only embedders (lose cross-lingual). Rejected to preserve bilingual parity.

## D4 — Vector store: keep Qdrant (embedded local / server cloud)

- **Decision**: Keep **Qdrant** behind a `VectorStore` interface — embedded (local path) for
  offline, server (Docker) for cloud — chosen by config.
- **Rationale**: Qdrant is natively deployment-agnostic (same client/API for embedded and
  server), supports named vectors (dense + sparse) for hybrid, and payload filtering for
  per-corpus / per-commentator scoping (Principle III). Already integrated.
- **Alternatives considered**: Chroma (earlier in project; less suited to hybrid + scale),
  FAISS (no payload/filtering, more glue), pgvector (adds a DB dependency offline). Rejected.

## D5 — Retrieval: hybrid (dense + sparse, RRF) + optional rerank, pasuk-anchored

- **Decision**: Hybrid retrieval fusing bge-m3 **dense** and **sparse** results via
  **Reciprocal Rank Fusion**, then an **optional reranking** stage (`bge-reranker-v2-m3`)
  enabled in the cloud profile and optional/off locally. Results are pasuk-anchored and
  grouped per commentator, deduped, similarity-sorted.
- **Rationale**: Torah queries hinge on exact terms — commentator names ("רש״י"), specific
  references — where lexical/sparse matching complements semantic search; this most directly
  serves grounding accuracy (Principle I). Reranking sharpens ordering when compute allows;
  making it optional preserves the laptop budget (Principle II/VI). The eval harness (D7)
  decides whether local reranking is worth enabling.
- **Alternatives considered**: dense-only (simpler/faster but misses exact-term matches —
  available as a config mode and the fallback if hybrid underperforms on the laptop);
  BM25 via a separate index (redundant given bge-m3 sparse). 

## D6 — Orchestration: thin custom Python, no heavy LLM framework

- **Decision**: A small custom `pipeline/` orchestrates query → retrieve → rank → generate →
  cite. No LangChain/LlamaIndex.
- **Rationale**: Grounding and citation enforcement are the product's core and must be fully
  controlled and inspectable (Principle I); a heavy framework adds indirection and hidden
  behavior against Principle VI. The pipeline is small enough to own directly.
- **Alternatives considered**: LlamaIndex/LangChain (faster scaffolding, but opaque
  retrieval/prompt control and heavier deps) — rejected for the core; may be revisited only
  if a concrete need appears.

## D7 — Trustworthiness: evaluation harness over 100+ Tanakh questions

- **Decision**: An `eval/` harness scores retrieval quality (did the expected source appear
  in top-K?) and answer grounding (are claims backed by retrieved/cited sources?) over a
  versioned set of **100+** Tanakh questions with expected sources, runnable on demand and
  comparable across runs. It is the gate for retrieval/prompt/corpus changes.
- **Rationale**: Principle V — trust must be measured, not felt. Same harness runs in both
  profiles to verify parity (SC-006) and detect regressions (SC-008).
- **Alternatives considered**: manual spot-checking (not reproducible), LLM-as-judge only
  (useful as a secondary signal but anchored to expected-source checks to avoid circularity).

## D8 — Dynamic corpus: a CorpusRegistry + uniform chunk schema

- **Decision**: A `CorpusRegistry` describes each work (id, language(s), source adapter,
  reference scheme, license) and a **uniform chunk schema** carries every text and commentary
  with its canonical reference and corpus id. Ingestion supports **incremental add** and
  **partial re-index**. Adding Gemara/Halacha later = register a new work + run ingestion.
- **Rationale**: Principle III — growth must be data/config, never an architecture change.
  Payload-filtered Qdrant search scopes retrieval per corpus without new code.
- **Alternatives considered**: per-corpus bespoke pipelines (violates III), one giant
  undifferentiated index (loses scoping/citation precision). Rejected.

## D10 — Dual retrieval: vector similarity + Sefaria link-graph traversal

- **Decision**: Complement vector retrieval (D5) with **link-based retrieval** that follows
  explicit edges — Sefaria's **Links graph** (`Link` entity) and `anchor_ref` **chains**
  (including supercommentary, `anchor_kind=commentary`). A query can (a) vector-search for the
  relevant anchor pesukim, then (b) **expand along links/anchors** to gather the Rishonim on
  them, the supercommentaries explaining those Rishonim, and — across corpora — the Acharonim
  and Halacha derived from them.
- **Rationale**: Two capabilities the user requires cannot be served by similarity alone:
  - *"Who explains the machloket between Rashi and Ramban here?"* → needs supercommentaries
    whose `anchor_ref` points at Rashi/Ramban's comment (an anchor chain), not texts that are
    merely semantically similar.
  - *A lesson that flows pasuk → Rishonim → Acharonim → Halacha* → needs the explicit chain of
    transmission (link edges across works), which similarity does not encode.
  This directly serves Principle I (grounding along a real chain) and Principle III (the link
  graph grows with each added corpus).
- **Scope**: Within the Tanakh MVP, link/anchor expansion connects pesukim ↔ their
  commentaries ↔ supercommentaries (once those texts are loaded). The full cross-corpus chain
  (Halacha/Acharonim) activates automatically as those corpora are registered — no code change.
- **Alternatives considered**: vector-only (rejected — misses anchor chains and cross-corpus
  transmission); building our own cross-reference graph (rejected — Sefaria already provides a
  curated Links graph; reuse it). The old project already used the Sefaria Linker/Links API.

## D11 — Supercommentaries & Halacha as planned Works (data/config, post-MVP content)

- **Decision**: Treat supercommentaries (Mizrachi, Gur Aryeh, Sifsei Chachamim…) and halachic
  works (Shulchan Aruch, Tur, Mishneh Torah, responsa) as **future `Work`s** registered via the
  CorpusRegistry. The schema (`anchor_kind`, `Link`) and retrieval (D10) already support them;
  only the data needs loading.
- **Rationale**: Principle III — adding them is a data/config operation, keeping the MVP lean
  (Principle VI) while not precluding the user's full vision.
- **Alternatives considered**: special-casing supercommentary/halacha in code (rejected —
  violates III).

## D9 — Deployment profiles via a single Config/Profile object

- **Decision**: One `Profile` (e.g. `local` / `cloud`) resolved from env/config selects every
  backend (embedding device, vector store mode + URL/path, LLM backend + model, reranker
  on/off). No code branches on profile beyond backend construction.
- **Rationale**: Principle II — same code, config-only difference; enables profile-parity
  testing.
- **Alternatives considered**: separate entrypoints/branches per profile (drift risk),
  feature flags scattered through logic (unmaintainable). Rejected.

## Open items deferred to implementation (non-blocking)

- Exact local reranking on/off default — decided empirically via the eval harness on the
  target laptop.
- Final cloud model id and Nebius endpoint specifics — config, set at product time.
- Chunking parameters (size/overlap) revisited against eval once measured.

## Implementation status notes (2026-06-10, T039)

- The reused legacy vectors are **dense-only** (embedded with sentence-transformers before
  the redesign), so the local profile currently runs the D5 **dense-only fallback**;
  `BgeM3Embedding` falls back to sentence-transformers when FlagEmbedding is absent.
  Full hybrid (dense+sparse) activates after a one-time re-embed with FlagEmbedding.
- Local reranker default stays **off** until measured: the tuning run (rerank on vs off
  over `eval/tanakh_v1.jsonl`) requires DictaLM pulled via Ollama on the target laptop.
  The retrieval-only gate (`scripts/run_eval.py --retrieval-only`) runs without the LLM.
