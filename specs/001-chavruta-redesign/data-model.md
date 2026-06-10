# Phase 1 Data Model: Chavruta.AI Redesign

Derived from the spec's Key Entities and the dynamic-corpus / grounding requirements. This
describes the conceptual model and the concrete **chunk schema** that flows through
ingestion → embedding → store → retrieval → generation.

## Core entities

### Work (Corpus unit)
A body of texts added as a unit (Tanakh today; Gemara, Halacha, Emunah later).
- `work_id` (stable slug, e.g. `tanakh`, `bavli`, `shulchan_aruch`)
- `title_he`, `title_en`
- `kind` (`scripture` | `commentary_collection` | `talmud` | `halacha` | `emunah` | …)
- `languages` (e.g. `["he","en"]`)
- `reference_scheme` (how citations are formed, e.g. book/chapter/verse; daf/amud)
- `source_adapter` (which ingestion adapter produced it, e.g. `sefaria`)
- `license` / `attribution`
- `version` / `fetched_at`
- **Rules**: adding a Work is a data/config operation (Principle III); `work_id` is unique
  and immutable once indexed.

### Commentator
A classical author whose commentaries are attributed and distinguished.
- `commentator_id` (e.g. `rashi`, `ramban`, `ibn_ezra`)
- `name_he`, `name_en`
- `aliases` (for query matching, e.g. "רש״י", "Rashi")
- **Rules**: every Commentary chunk is attributed to exactly one Commentator (Principle I).

### SourceText (primary text unit)
A unit of primary sacred text (e.g. a verse).
- `ref` (canonical reference, e.g. `Genesis 1:3` / `בראשית א:ג`)
- `work_id`
- `position` (book, chapter, verse / structural coordinates for ordering + anchoring)
- `text_he`, `text_en` (EN where available)
- `deep_link` (resolvable link back to the source)

### Commentary (secondary text unit)
A commentator's remark tied to a specific anchor. The anchor is usually a SourceText, **but
may itself be another Commentary** — this is how **supercommentary** (commentary-on-
commentary, e.g. Mizrachi / Gur Aryeh / Sifsei Chachamim on Rashi) is represented.
- `ref` (the commentary's own reference)
- `work_id`, `commentator_id`
- `anchor_ref` (the `ref` it comments on — a SourceText **or** another Commentary)
- `anchor_kind` (`source` | `commentary`) — distinguishes direct commentary from supercommentary
- `text_he`, `text_en`
- `deep_link`

### Link (cross-reference / chain edge)
An explicit connection between two refs, sourced from Sefaria's Links graph (not inferred by
similarity). Powers following the chain of transmission across corpora — e.g. a pasuk → the
Rishonim on it → the Acharonim → the Halacha derived from it.
- `from_ref`, `to_ref`
- `from_work_id`, `to_work_id`
- `link_type` (e.g. `commentary`, `quotation`, `reference`, `halacha`)
- **Rules**: links are directional edges used by **link-based retrieval** (alongside vector
  retrieval) to traverse from an anchor to related material in *other* works. Adding a new
  corpus brings its links with it (data/config — Principle III).

### Chunk (the indexed unit — unified schema)
Both SourceText and Commentary are normalized into **Chunks** for embedding/retrieval. One
uniform schema keeps the pipeline corpus-agnostic (Principle III).

| field | type | notes |
|-------|------|-------|
| `chunk_id` | string | stable unique id (`work_id:ref[:seq]`) |
| `work_id` | string | FK → Work |
| `unit_type` | enum | `source` \| `commentary` |
| `ref` | string | canonical reference of this chunk |
| `anchor_ref` | string? | for `commentary`: the ref it comments on — a SourceText **or** another Commentary (supercommentary) |
| `anchor_kind` | enum? | `source` \| `commentary` — set for `commentary` chunks |
| `commentator_id` | string? | for `commentary` |
| `position` | object | structural coords for ordering/anchoring |
| `lang` | enum | `he` \| `en` (per-language chunk) |
| `text` | string | the chunk text in `lang` |
| `text_he` | string | always present (HE is first-class — Principle IV) |
| `text_en` | string? | when available |
| `deep_link` | string | resolvable citation target |
| `dense_vector` | float[1024] | bge-m3 dense (stored in vector backend) |
| `sparse_vector` | map | bge-m3 learned-sparse (lexical) |

- **Rules**:
  - A chunk's `text` must be present and non-empty (no empty/placeholder indexing).
  - `commentary` chunks MUST carry `commentator_id` + `anchor_ref` (attribution, anchoring).
  - Chunks are filterable by `work_id` / `commentator_id` for scoped retrieval and citation.

### Citation
The link between a claim in an answer and the chunk it is grounded in.
- `chunk_id`, `ref`, `commentator_id?`, `deep_link`
- `quote` (the grounding snippet)
- **Rules**: every claim in a generated answer maps to ≥1 Citation; a Citation must resolve
  to a real, retrieved chunk (Principle I; FR-001/002/004).

### Conversation / Question
- `question_text`, `lang` (detected/declared)
- `intent` (`qa` | `explain` | `lesson`; `halacha` reserved/deferred)
- `turns` (ordered prior turns — **in-session only**, not persisted, per clarification)
- `named_refs` / `named_commentators` (detected references that bias retrieval)

### Answer
- `text` (in the question's language)
- `citations` (Citation[])
- `grounded` (bool) / `no_source` (bool — honest empty state, FR-003)
- `caveats` (e.g. the halachic caveat when intent = halacha)

### LessonPlan (intent = lesson)
- `topic` / `parasha`
- `sections` (each: heading, `source_refs`, explanation, discussion_points)
- `citations` — every referenced source resolves (FR-008)

### EvaluationItem
- `question`, `lang`
- `expected_refs` (sources that should be retrieved)
- `grounding_checks` (assertions the answer must satisfy)
- Used by the harness to score retrieval@K and grounding (Principle V; 100+ items).

## Relationships

```text
Work 1───* Chunk
Work 1───* SourceText / Commentary  (normalized into Chunk)
Commentator 1───* Commentary (Chunk where unit_type=commentary)
SourceText  1───* Commentary        (via anchor_ref, anchor_kind=source)
Commentary  1───* Commentary        (via anchor_ref, anchor_kind=commentary → supercommentary)
Chunk *───* Chunk                   (via Link — cross-corpus chain edges)
Chunk 1───* Citation               (a citation points at one chunk)
Answer  *───* Citation
Question 1───1 Answer
EvaluationItem *───* SourceText     (expected_refs)
```

## Lifecycle / state

- **Ingestion**: source adapter → normalize → chunk → (embed) → upsert into store. Supports
  **incremental add** (new Work or new refs) and **partial re-index** without full rebuild
  (FR-015).
- **Query**: detect lang + named refs → embed query → hybrid search (filterable by work) →
  **optional link-expansion** (follow `Link` edges and `anchor_ref` chains from the anchor
  pesukim to related material — supercommentaries, and across corpora for lessons) →
  fuse/rank/rerank → build grounded prompt → generate → enforce citations → answer or
  honest `no_source`.
