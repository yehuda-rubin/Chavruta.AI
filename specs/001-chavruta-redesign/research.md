# Phase 0 Research: Chavruta.AI Redesign

Key technical decisions, each with rationale and the alternatives considered. All choices
are constrained by the Constitution (esp. II deployment-agnostic, III dynamic corpus, VI
simplicity) and the offline envelope (CPU-only 16GB laptop).

> **Update 2026-06-10 — Dicta-LM 3.0 (released 2026-02)**: Dicta released DictaLM-3.0 in
> 24B (Mistral-Small-3.1), Nemotron-12B, and 1.7B (Qwen3) sizes, 65k context, with
> **official GGUFs** (incl. Nemotron-12B-Instruct-GGUF and 1.7B-Thinking-GGUF).
>
> **DECISION (user, 2026-06-10) — local default is DictaLM-3.0-1.7B (Q8_0, 1.83GB).**
> The real memory budget on the target laptop is ~5-6GB free under normal use (OS +
> apps occupy ≥60% of 16GB), which rules out: 12B Q4 (~7.2GB — dead), and the previous
> default 2.0-7B Q4 (~4.4GB + bge-m3 ≈ 7.4GB — too heavy for daily use; dropped).
> The 1.7B totals ≈ 4.2GB with bge-m3 — comfortable. Official GGUF:
> `hf.co/dicta-il/DictaLM-3.0-1.7B-Thinking-GGUF:Q8_0` via Ollama; the generation layer
> strips `<think>` traces before citation enforcement. Quality is validated by the eval
> harness; the cloud profile carries the heavy models (3.0-24B/12B via Nebius/GPU).

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
- **Concrete roadmap → D12.**

## D9 — Deployment profiles via a single Config/Profile object

- **Decision**: One `Profile` (e.g. `local` / `cloud`) resolved from env/config selects every
  backend (embedding device, vector store mode + URL/path, LLM backend + model, reranker
  on/off). No code branches on profile beyond backend construction.
- **Rationale**: Principle II — same code, config-only difference; enables profile-parity
  testing.
- **Alternatives considered**: separate entrypoints/branches per profile (drift risk),
  feature flags scattered through logic (unmaintainable). Rejected.

## D12 — Corpus-expansion roadmap: Mishnah → Shulchan Aruch + Mishnah Berurah → Talmud (user, 2026-06-13)

- **North-star (user, 2026-06-13): the target corpus is the *entire Sefaria library*.** The
  phases below are not the scope ceiling — they are the **ingestion order** toward full-Sefaria
  coverage. Everything in Sefaria (Tanakh, Mishnah, Talmud Bavli + Yerushalmi, Halacha, Midrash,
  Kabbalah, Machshava, Responsa, modern works…) is in eventual scope; the roadmap just sequences
  *what loads first* by value and ingestion difficulty.
- **What "all of Sefaria" implies architecturally** (does not change the schema — Principle III —
  but changes ingestion + ops):
  - **Ingestion must become index-driven, not hand-listed.** `SefariaAdapter.fetch_*` currently
    takes explicit `refs`; full coverage needs a crawler that walks Sefaria's **Index / table-of-
    contents API** (categories → works → every ref) to enumerate the library systematically and
    resumably. This is the main *new code* the goal requires — a generic traversal, still one
    adapter, no per-work special-casing.
  - **Scale is now millions of segments** → Qdrant **server** is mandatory in every profile
    (embedded mode is for the Tanakh-sized slice only); embedding becomes a staged GPU batch job;
    storage + reload cost must be budgeted (cf. D4 / Implementation status notes).
  - **Per-work licensing must be captured and respected** — Sefaria texts vary (CC0 / CC-BY /
    restricted). `Work.license`/`attribution` already exist; ingestion MUST populate them per work
    and the crawler MUST honor texts that can't be redistributed.
  - **Eval stays sampled, honesty stays universal** — `expected_refs` can't be authored for the
    whole library; the retrieval eval remains a growing *sample*, while the honesty/grounding
    gates (SC-002, Principle I) apply to everything ingested.
- **Decision**: Concretize D11 into a **phased content roadmap** toward that north-star, each phase
  a data/config operation through `SefariaAdapter` + `CorpusRegistry` — **no change** to retrieval,
  ranking, generation, or schema (Principle III; guarded by extensibility test T024a / SC-005).
  Phases are ordered by ingestion difficulty, not importance, so each phase validates against the
  eval harness before the next begins (Principle V):
  1. **Mishnah** — `kind=mishnah` (or `scripture`-like), `reference_scheme="tractate/chapter/mishnah"`.
     Cleanest: clean Hebrew, fully structured, one Mishnah = one chunk. Lowest risk; validates
     the non-Tanakh ingestion path end-to-end.
  2. **Shulchan Aruch + Mishnah Berurah (a linked pair)** — SA `kind=halacha`,
     `reference_scheme="section/siman/seif"`; MB ingested as a **commentary Work anchored to SA**
     (`unit_type=commentary`, `anchor_kind=source`, `anchor_ref` = the SA seif via Sefaria's Links
     graph). The value is the **SA↔MB linkage** (seif ↔ s"k), which D10's `LinkExpander` already
     traverses — load it as links, do not flatten. **Activates US4 / FR-009**: once a halachic
     corpus is loaded the halachic intent path goes live and **every** halachic answer MUST carry
     the "not a substitute for a rav / not a binding pesak" caveat (Principle VIII, SC-007); the
     eval set must add halachic items asserting that caveat.
  3. **Talmud Bavli + commentaries (Rashi, Tosafot, …)** — the hard phase, deferred until 1–2 are
     solid. `kind=talmud`, `reference_scheme="daf/amud"`. **Chunking decision (user): chunk = one
     Sefaria text segment** (e.g. `Shabbat 2a:1`, `2a:2` …) — Sefaria's own division of each amud
     into numbered segments. `position` keeps `{tractate, daf, amud, segment}` for ordering; the
     daf/amud stays the citable unit. **Rashi/Tosafot/other mefarshim are separate commentary
     `Work`s** anchored to their gemara segment via the Links graph (`anchor_kind=source`),
     exactly as the Tanakh commentators are — so the dialectical layout (gemara + Rashi + Tosafot
     on the same segment) is reconstructed by link-expansion at query time, not by special code.

- **Rambam (user, 2026-06-13) — a multi-work author whose books slot across the phases above,
  not one monolithic phase**:
  - **Peirush HaMishnayot (Commentary on the Mishnah)** → loads with **phase 1**, as a commentary
    `Work` anchored to each Mishnah (`anchor_kind=source`). Natural pairing with the Mishnah.
  - **Mishneh Torah (Yad HaChazakah)** → loads with **phase 2** (`kind=halacha`,
    `reference_scheme="sefer/hilchot/perek/halacha"`). Highly structured. Its classical nosei
    kelim (Maggid Mishneh, Kesef Mishneh, Lechem Mishneh, Hagahot Maimoniyot) are further
    commentary `Work`s anchored to the halacha — same supercommentary pattern as Tanakh.
  - **Sefer HaMitzvot** → with phase 2; structured list of the 613, anchored to its mitzvot.
  - **Moreh Nevuchim (Guide for the Perplexed)** → `kind=emunah`, a **separate philosophical
    register** from the halachic/exegetical core; add it on its own track (after the core chain
    works) since it serves a different intent and its Hebrew is a translation (Ibn Tibbon/Kapach).
  - Rambam is also a **chain hub**: Mishneh Torah is a node on the halachic spine
    (Talmud → Rambam → Tur/Beit Yosef → Shulchan Aruch → Mishnah Berurah), so loading it enriches
    the D10 link-expansion across the other halachic works.

- **Candidate backlog (prioritized by chain-completion + structuredness, not yet scheduled)**:
  - **Tur (Arba'ah Turim) + Beit Yosef** — *highest-value next halachic addition.* The SA is
    literally structured on the Tur, and the Beit Yosef bridges Rambam→Tur→SA; loading it
    **completes the halachic spine** so a single question can traverse Talmud → Rambam → Tur → SA
    → MB. Structured, cheap to ingest. Strong recommendation.
  - **Mishnah commentaries — Bartenura, Tosafot Yom Tov** — pair with phase 1; the standard
    learning layer on Mishnah, structured, low risk.
  - **Midrash (Rabbah, Tanchuma)** — aggadic, densely linked to pesukim; high value for
    **lessons/shiurim (US3)** and structured by parasha. Medium priority.
  - **Talmud Yerushalmi** — parallels the Bavli; same difficulty class, lower priority — after
    the Bavli phase proves the Talmud ingestion path.
  - **Defer / out of near-term scope**: She'elot uTeshuvot (responsa — huge, weakly structured,
    hard to anchor); Kabbalah/Zohar (Aramaic + interpretively sensitive — needs its own guardrail
    design, cf. Principle VIII spirit). Record but do not schedule.
- **Rationale**: Phasing by difficulty front-loads cheap validation: a regression after adding
  Mishnah (clean, small) is trivially attributable; a regression after Talmud (Aramaic, huge,
  dialectical) is not — so Talmud goes last, on a corpus whose other layers are already trusted.
  Chunking Talmud by Sefaria segment reuses a curated, stable division (matching how the Links
  graph anchors commentaries) instead of inventing our own sugya segmentation.
- **Open considerations (measure, don't assume)**:
  - **Aramaic retrieval** — bge-m3 covers Aramaic but quality is unverified here; the Talmud
    phase MUST extend the eval set with Aramaic/Talmud questions and gate on retrieval@K before
    acceptance (Principle V). Marginal hybrid lift may matter more on exact-term Talmud queries
    than it did on paraphrase-heavy Tanakh items (cf. T039).
  - **Scale → vector backend** — Talmud + commentaries is far larger than the 126k-chunk Tanakh
    corpus; per the measured embedded-Qdrant limits (Implementation status notes / D4), this phase
    almost certainly mandates **Qdrant server in Docker** even locally (config-only switch,
    `CHAVRUTA_QDRANT_MODE=server`). Budget GPU embedding time + Qdrant disk before ingesting.
  - **Dialectical reasoning** — RAG retrieves segments but does not natively model קושיא/תירוץ
    flow; segment-level chunking + link-expansion is the first cut, to be revisited against eval.

## D13 — Validate the existing product on Nebius (cloud profile) in parallel, on the current corpus first (user, 2026-06-13)

- **Decision**: Run cloud-profile (Nebius Token Factory) validation **concurrently** with the D12
  corpus expansion, but **against the current Tanakh corpus and the existing eval set first** —
  establish a stable cloud baseline before the corpus changes underneath it.
- **Rationale**: The two efforts test orthogonal axes — D12 changes the **corpus**
  (retrieval/grounding quality), D13 changes the **LLM + deployment layer** (cloud serverless
  generation vs local DictaLM). Running them in parallel is efficient, but changing both the model
  and the corpus at once makes any regression unattributable. Pin one: fix the corpus, swap the
  profile, run the **same** eval harness (`scripts/run_eval.py`) under `profile=cloud` → this both
  validates Nebius generation quality and exercises profile parity (SC-006) on known data. Only
  after the cloud baseline holds should expanded corpora be evaluated under it.
- **Cost note**: corpus expansion multiplies embedding time and Qdrant footprint, and cloud
  generation is per-token billed — measure both on a single source (Mishnah) before running the
  full batch (Principle VI: no surprise blowups).
- **Alternatives considered**: validate cloud only after the corpus is final (rejected — wastes
  the parallelism and delays catching cloud-specific issues); change corpus + model together
  (rejected — confounds attribution, violates the measurement discipline of Principle V).

## D14 — Thematic source tree for lesson generation (2026-06-16)

- **Problem**: `Intent.LESSON` currently dumps all retrieved + link-expanded chunks into the
  LLM prompt and lets the model impose structure. This is brittle: the LLM may reorder,
  over-weight, or omit layers of the transmission chain — the model does not natively "know"
  that a Shulchan Aruch seif is the *ruling* and a Talmudic passage is the *root*, or that
  Rashi is *interpretation* while Mishnah Berurah is *practical application*.
- **Decision**: Add a **`ThematicOrganizer`** post-retrieval step, executed only on
  `Intent.LESSON`, that clusters the retrieved + link-expanded sources into **named thematic
  slots** before passing them to generation:

  ```
  root_sources   — primary pesukim / Mishnah / Talmud segments on the topic
  interpretations — Rishonim & Acharonim explaining the root (Rashi, Rambam, …)
  rulings        — halachic conclusions (SA, MT, Tur, MB, responsa)
  applications   — practical examples, edge cases, machloket
  ```

  Each slot is populated by **source metadata** already available in the chunk schema
  (`work.kind`, `anchor_kind`, `corpus_id`) — no new LLM call needed for classification.
  Works with `kind=scripture|mishnah|talmud` go to `root_sources`; `kind=commentary` with
  `anchor_kind=source` go to `interpretations`; `kind=halacha` go to `rulings`, etc.
  Ambiguous chunks (e.g. a Rambam in Mishneh Torah that is both interpretation and ruling)
  are placed in the best-fitting slot by a small rule table, with a fallback to `interpretations`.

- **Interaction with D10**: `LinkExpander` already traverses the transmission chain
  (pasuk → Rishonim → Acharonim → Halacha). `ThematicOrganizer` sits *after* link expansion
  and organises its output — the two are complementary. The link graph provides the *connections*;
  the thematic organizer provides the *lesson structure*.

- **Generation impact**: The grounded prompt builder (`generation/grounded.py`) receives the
  organiser's output as a **structured dict** (not a flat list). It renders each slot as a
  labelled section header in the prompt (`## שורש — ## פרשנות — ## פסיקה`) so the LLM can
  produce a lesson that flows naturally from source to interpretation to ruling, grounded at
  every step (Principle I). The organizer must never drop a source — it only reorders.

- **Scope and preconditions**: The organizer is trivially useful even with Tanakh-only corpus
  (slot: `root_sources` + `interpretations`); it becomes fully expressive once Phase 2
  (SA + MT) is loaded and `rulings` slot fills. Implement the organizer before Phase 2
  ingestion so the lesson path is exercised and tested from the start.

- **Rationale**: Semantic similarity retrieves *relevant* sources; the link graph traverses
  *connected* sources; the thematic organizer ensures they arrive at generation in *pedagogical
  order* — the three layers together (D5 + D10 + D14) make lesson generation reliable rather
  than model-dependent. Keeps lesson structure in deterministic code, not in the LLM's
  discretion (Principle VI: simplicity and inspectability).

- **Alternatives considered**: letting the LLM structure the lesson from a flat source list
  (current — fragile, order-dependent, tested to drift on long source lists); a separate
  "structuring" LLM call before generation (rejected — doubles latency, adds cost, introduces
  a second grounding failure mode); a rigid template per topic (rejected — topics vary too
  much; the slot-based design is flexible enough without being fully open-ended).

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
- **Embedded-Qdrant load cost at 126k scale (measured)**: dense-only load ≈ 13 min;
  hybrid (dense+sparse) load is ~10-15× slower (sparse inverted-index updates in the
  SQLite-backed local mode; Qdrant itself warns above 20k points). One-time cost per
  reload; query latency is unaffected. If reloads become frequent, run Qdrant in local
  Docker (still fully offline) — same code, `CHAVRUTA_QDRANT_MODE=server`.
- **Embedded-Qdrant query cost at 126k scale (measured 2026-06-10)**: embedded local mode
  does brute-force scans (no HNSW). Dense-only query ≈ 6s; **hybrid query ≈ 35s** — fine
  for the batch eval gate, NOT acceptable for interactive chat (SC-004). Also,
  FlagEmbedding on CPU runs fp32 (~4.6GB RAM) vs the ST dense-only fallback (~2GB).
  **Recommendation for the local profile**: for interactive daily use either (a) run
  Qdrant server in local Docker — still fully offline, real HNSW + sparse indexes,
  millisecond queries, config-only switch; or (b) stay on the lightweight dense-only
  fallback. Full hybrid in pure-embedded mode is for batch evaluation only.
- **Hybrid corpus is live**: the full corpus was re-embedded on Kaggle GPU with
  FlagEmbedding (dense + sparse, `out/corpus_sparse.jsonl`) and loaded; the dense-only
  artifacts are archived in `out_dense_backup/`.
- **T039 outcome — eval results on the real corpus (2026-06-10, retrieval-only @8)**:
  dense 72.7% / hybrid **73.6%** retrieval; honesty **100%** (after the requested-work
  detection + clean reload; was 0% before). Hybrid lift is marginal (+0.9pp) on the
  current question set because most items are paraphrase-style (dense's strength); the
  measured-failure review also shows several "misses" that are legitimate parallel
  sources (e.g. the Devarim recounting of the Ten Commandments) not listed in
  `expected_refs` — true quality is higher than measured. Follow-ups recorded: broaden
  `expected_refs` with parallel passages; revisit hybrid + reranker after moving local
  serving to Docker Qdrant. **Local-profile default remains dense-only ST fallback for
  interactive use (RAM/speed); hybrid runs in the batch eval gate and in cloud.**
