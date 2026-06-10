<!--
Sync Impact Report
==================
Version change: 1.0.0 → 1.1.0
Ratification: initial adoption (2026-06-09); amended same day
Modified principles: none
Added principles:
  (1.0.0) I–VII as below
  (1.1.0) VIII. Halachic Humility & Deference
Added sections: Additional Constraints; Development Workflow & Quality Gates; Governance
Templates requiring updates:
  ✅ .specify/templates/plan-template.md (Constitution Check gate references this file generically — no edit needed)
  ✅ .specify/templates/spec-template.md (no constitution-specific sections to sync)
  ✅ .specify/templates/tasks-template.md (no constitution-specific task types to sync)
Follow-up TODOs: none
-->

# Chavruta.AI Constitution

Chavruta.AI is a trustworthy Torah study partner: it answers questions on the sacred
texts by **retrieving the actual sources** and generating a **grounded, cited** answer —
the way a *chavruta* learns straight from the text. This constitution defines the
non-negotiable principles that govern every design and implementation decision.

## Core Principles

### I. Grounded, Never Invented (NON-NEGOTIABLE)

Every factual claim in an answer MUST be anchored in a source that was actually
retrieved for that question, and MUST carry a citation (reference + deep-link) the user
can follow back to the original text.

- The knowledge lives in the **retrieval index, never in the model weights**. The LLM is
  the *voice*, not the *memory*.
- If no relevant source is retrieved, the system MUST say so plainly — it MUST NOT
  fabricate a *davar Torah*, a citation, or an attribution to a commentator.
- Fine-tuning, if ever used, may shape *style or phrasing only* — never knowledge.

**Rationale**: This is the entire reason the project exists. A model that *memorizes*
Torah hallucinates; a model that *retrieves* it cites chapter and verse. Violating this
principle makes the system actively harmful for sacred study, so it is absolute.

### II. Deployment-Agnostic Core

The same codebase MUST run both **fully offline on a personal machine** and as a
**scalable cloud product**. The difference between profiles is **configuration only** —
never forked code paths or separate branches.

- Embedding, vector store, LLM backend, and source-enrichment are pluggable behind
  stable interfaces; the active implementation is chosen by config/env.
- A change that works in one profile MUST NOT silently break the other.

**Rationale**: The project serves two real goals — the author's private offline study
and a future product with users — and they must not diverge into two systems to maintain.

### III. Dynamic, Extensible Corpus

Growing the corpus — adding texts, commentators, or an entirely new body of work
(Mishnah, Talmud, Halacha, etc.) — MUST be a **data/config operation**, not an
architectural change.

- The data schema and ingestion pipeline are designed for open-ended growth from day one.
- Adding a new source MUST NOT require modifying retrieval, ranking, or generation logic.
- Re-indexing and incremental additions MUST be supported without rebuilding from scratch.

**Rationale**: The author intends to keep expanding the system continuously; the
architecture must make that cheap and safe, not a rewrite each time.

### IV. Bilingual by Design

Retrieval and generation MUST both operate in the language of the question (Hebrew or
English), and Hebrew is a first-class language end to end.

- Every stored text carries its Hebrew form; English is provided where available.
- A Hebrew question retrieves Hebrew sources; an English question retrieves the same
  underlying source via its translation. The answer is written in the question's language
  and quotes the Hebrew source.
- Hebrew RTL rendering and Hebrew-aware text handling are requirements, not afterthoughts.

**Rationale**: The audience is bilingual and the sources are Hebrew; the system is
useless if either language is a second-class citizen.

### V. Measurable Trustworthiness

Retrieval quality and answer grounding MUST be measured by an automated evaluation
harness, and trustworthiness MUST NOT regress.

- A versioned evaluation set (questions → expected sources / grounding checks) exists and
  runs on demand.
- A change that lowers the grounding/retrieval score MUST NOT be merged without explicit,
  documented justification.
- "It feels better" is not evidence; the score is.

**Rationale**: Trust is the product. Without measurement, quality silently erodes and the
core promise (Principle I) cannot be defended.

### VI. Simplicity First (YAGNI)

Start from the simplest solution that works; add complexity only when a concrete,
present need justifies it.

- There is always a working end-to-end system; features land incrementally on top of it.
- Speculative abstraction, premature optimization, and unused configuration are rejected.
- Complexity MUST be justified against the principles above, or removed.

**Rationale**: A small, comprehensible system that runs offline on a laptop and scales to
a product is only achievable if it stays simple at its core.

### VII. User Experience

The system MUST be usable and respectful of the person studying — for both the private
user and future product users.

- Answers are clear, well-structured, and lead the user *into* the sources, not away from
  them; citations are clickable and verifiable.
- The interface is responsive: the user gets feedback quickly and is never left guessing
  whether the system is working.
- Hebrew and English presentation are both polished (correct RTL/LTR, readable typography).
- Errors and "no source found" states are communicated honestly and helpfully.

**Rationale**: A trustworthy answer that is unreadable or frustrating to reach does not
serve the goal of helping someone learn.

### VIII. Halachic Humility & Deference

When the system addresses questions of *halacha* (practical Jewish law), it MUST present
sourced guidance — never an unqualified, binding ruling — and MUST defer final
authority to a human rav.

- A halachic answer MUST present the relevant sources and opinions, and MUST clearly
  carry the caveat that **it is not a substitute for a competent rav** and is not a
  binding *pesak*.
- Where authorities disagree, the system MUST surface the disagreement rather than
  silently choosing one ruling as definitive.
- This applies specifically to practical halachic rulings; explanation, study, and
  source-presentation across all texts remain governed by Principles I–VII.

**Rationale**: Issuing *pesak halacha* carries real-world religious consequence and
rightly belongs to a human posek who knows the questioner and the full context. The
system's role is to inform and direct study, not to replace rabbinic authority.

## Additional Constraints

- **Open sources**: Texts are drawn from open, free sources (e.g. Sefaria). Licensing and
  attribution of source texts MUST be respected and documented.
- **Privacy**: In the personal/offline profile, study data and queries stay on the user's
  machine. In the product profile, user data handling MUST be explicit and minimal.
- **Reproducibility**: Corpus construction and indexing MUST be reproducible from scripts
  and documented configuration — no undocumented manual steps in the critical path.
- **Portability of data**: Embeddings and corpus artifacts are stored in a
  store-agnostic, portable form so the vector backend can be swapped (Principle II).

## Development Workflow & Quality Gates

- **Spec-driven**: Significant work flows through Spec Kit — constitution → specify →
  (clarify) → plan → tasks → implement. Plans MUST pass a Constitution Check before tasks.
- **Always-working main**: The system on the main branch always runs end to end; changes
  are incremental and never leave the core broken.
- **Evaluation gate**: Changes that touch retrieval, ranking, prompting, or the corpus
  MUST be checked against the evaluation harness (Principle V) before they are considered
  done.
- **Profile parity check**: Changes that touch a pluggable backend MUST be validated to
  not break the other deployment profile (Principle II).

## Governance

This constitution supersedes ad-hoc practice. When a decision conflicts with a principle,
the principle wins or the principle is formally amended — not quietly ignored.

- **Amendments** require: a written rationale, a version bump per the policy below, and an
  update to any artifacts the amendment affects (templates, docs, plans).
- **Versioning policy** (semantic):
  - **MAJOR**: a principle is removed or redefined in a backward-incompatible way.
  - **MINOR**: a new principle/section is added or guidance is materially expanded.
  - **PATCH**: clarifications, wording, and non-semantic refinements.
- **Compliance**: Every plan's Constitution Check and every review MUST verify alignment
  with these principles. Principle I is absolute and MUST never be traded away for
  convenience, performance, or scope.

**Version**: 1.1.0 | **Ratified**: 2026-06-09 | **Last Amended**: 2026-06-09
