# Feature Specification: Chavruta.AI — Trustworthy Jewish-Text Study Partner (Full Redesign)

**Feature Branch**: `001-chavruta-redesign`

**Created**: 2026-06-09

**Status**: Draft

**Input**: User description: "Full from-scratch redesign of Chavruta.AI — a trustworthy
Jewish-text study partner that retrieves actual sources and gives grounded, cited answers.
Acts like a chavruta or rav across the Jewish bookshelf; runs fully offline on a personal
machine and can grow into a real product; architecture is dynamic so new texts and corpora
can be added continuously. Capabilities (priority order): grounded Q&A, explain
commentators, lesson/shiur prep, halachic guidance (with the 'not a substitute for a rav'
caveat). Bilingual Hebrew/English, Hebrew first-class. MVP goes deep on Tanakh first."

## Clarifications

### Session 2026-06-09

- Q: Halachic guidance (P4) in the Tanakh-first MVP, which has no halachic source texts
  (Shulchan Aruch, Tur)? → A: Defer P4 until a halachic corpus is added; the MVP delivers
  P1–P3 over Tanakh only. (A sourced halachic answer is impossible without halachic
  sources, per Principle I.)
- Q: What local (offline) hardware envelope must the system run on comfortably? → A: A
  modest laptop — CPU-only at query time, ~16GB RAM, no dedicated/required GPU.
- Q: How much conversational context must the MVP retain? → A: In-session context only
  (remembers the current conversation's turns); no persistence across sessions.
- Q: Initial size of the trustworthiness evaluation set? → A: A larger set of 100+ Tanakh
  questions with expected sources, grown over time.
- Q: Lessons often flow Torah → Rishonim → Acharonim → Halacha, and users want the
  commentators who explain a Rashi–Ramban dispute. Are these in scope? → A: Yes, fold them
  into the design now: (1) **link-based retrieval** over Sefaria's Links graph (alongside
  vector search) to follow the chain of transmission across corpora; (2) **anchor chains /
  supercommentary** (a commentary whose anchor is another commentary) so the system can bring
  commentators who explain a dispute; (3) supercommentaries and halachic works are planned
  `Work`s added via the corpus registry. The cross-corpus content (Halacha/Acharonim/
  supercommentary) activates as those corpora are loaded — the Tanakh MVP delivers the
  within-Tanakh version.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Grounded answer with citations (Priority: P1)

A learner asks a question about a Tanakh text — in Hebrew or English — and receives an
answer that is built **only** from sources the system actually retrieved (the verse plus
relevant classical commentators). Every claim is followed by a citation that links back to
the exact source, so the learner can verify it. If nothing relevant is found, the system
says so honestly rather than inventing an answer.

**Why this priority**: This is the core promise and the reason the project exists (a
trustworthy *chavruta* that never fabricates Torah). Without it, nothing else matters. It
is the minimal viable product on its own.

**Independent Test**: Ask a set of known Tanakh questions (HE and EN) and verify each
answer (a) cites real, retrievable sources, (b) contains no claim absent from those
sources, and (c) returns an honest "no source found" when the corpus lacks an answer.

**Acceptance Scenarios**:

1. **Given** the Tanakh corpus is indexed, **When** the learner asks "What does Rashi say
   about the creation of light?", **Then** the system returns an answer grounded in
   Rashi's actual comment with a clickable citation to that source.
2. **Given** a Hebrew question, **When** the learner asks "מה אומר רד״ק על ספר יונה?",
   **Then** the answer is written in Hebrew, quotes the Hebrew source, and cites it.
3. **Given** a question with no relevant source in the corpus, **When** the learner asks
   it, **Then** the system clearly states no grounded source was found and does not
   fabricate one.
4. **Given** any answer, **When** the learner inspects a citation, **Then** following it
   leads to the actual cited text.

---

### User Story 2 - Explain and compare commentators (Priority: P2)

A learner wants to understand a specific commentator's view on a verse, or how several
commentators differ. The system presents each commentator's position grounded in that
commentator's actual words, and — when asked — lays out the differences and points of
disagreement between them, each attributed to its source.

**Why this priority**: Understanding the *mefarshim* is central to real Torah study and
directly extends the grounded-answer core; it is the natural second capability.

**Independent Test**: Ask for a single commentator's explanation on a verse, and
separately ask for a comparison among several; verify each position is attributed to the
correct commentator and grounded in retrieved text, with disagreements surfaced rather
than flattened.

**Acceptance Scenarios**:

1. **Given** a verse with multiple commentaries, **When** the learner asks "Explain what
   Ramban says here", **Then** the system explains Ramban's view grounded in his words,
   cited.
2. **Given** the same verse, **When** the learner asks "How do Rashi and Ibn Ezra differ
   here?", **Then** the system presents both views, attributes each correctly, and
   highlights the disagreement.
3. **Given** a commentator who does not comment on the requested verse, **When** asked
   about that commentator there, **Then** the system states that this commentator has no
   comment on that verse rather than inventing one.

---

### User Story 3 - Prepare a structured lesson (shiur) (Priority: P3)

A teacher or learner asks the system to help prepare a lesson on a topic or a parasha. The
system produces a structured outline grounded in retrieved sources: the key sources to
study, a suggested structure/flow, and discussion points — all with citations so the
preparer can go straight to the texts.

**Why this priority**: A high-value capability that builds on grounded retrieval and
commentator explanation, but is more complex and depends on the first two being solid.

**Independent Test**: Request a lesson on a defined topic/parasha and verify the output is
a coherent structure whose every cited source is real and retrievable, and whose
discussion points are tied to those sources.

**Acceptance Scenarios**:

1. **Given** the Tanakh corpus, **When** the learner asks "Prepare a lesson on the theme
   of teshuva in the book of Jonah", **Then** the system returns a structured outline with
   cited sources, a suggested flow, and discussion points.
2. **Given** a parasha name, **When** the learner asks for a shiur on it, **Then** the
   outline draws on sources from that parasha with citations.
3. **Given** a lesson output, **When** the preparer reviews it, **Then** every source
   referenced is real and links back to its text.

---

### User Story 4 - Halachic guidance with deference (Priority: P4 — deferred post-MVP)

**Scope note**: This capability is **deferred until a halachic corpus (e.g. Shulchan
Aruch, Tur, responsa) is added**. The Tanakh-first MVP delivers User Stories 1–3 only,
because grounded halachic guidance is impossible without halachic source texts
(Principle I). The behavior below governs P4 once that corpus exists.

A learner asks a question of practical Jewish law. The system presents sourced guidance —
the relevant sources and, where they differ, the range of opinions — and **always**
accompanies it with a clear caveat that it is not a substitute for a competent rav and is
not a binding ruling. It never issues an unqualified, definitive *pesak*.

**Why this priority**: Important to the vision but the most sensitive; it depends on
mature, trustworthy retrieval and explanation first, and carries the strongest guardrail
(Constitution Principle VIII).

**Independent Test**: Ask a set of halachic questions and verify each response (a) is
grounded in real sources, (b) surfaces disagreement when authorities differ, and (c)
always carries the "not a substitute for a rav / not a binding pesak" caveat.

**Acceptance Scenarios**:

1. **Given** a halachic question, **When** the learner asks it, **Then** the system gives
   sourced guidance and includes the caveat that it is not a substitute for a rav.
2. **Given** a question where authorities disagree, **When** the learner asks it, **Then**
   the system surfaces the disagreement rather than presenting one ruling as definitive.
3. **Given** any halachic response, **When** the learner reads it, **Then** the caveat is
   present and the response never claims to be a binding pesak.

---

### Edge Cases

- **Ambiguous reference**: The learner names a verse/commentator imprecisely or in a mix
  of Hebrew and English — the system resolves it sensibly or asks a brief clarifying
  question rather than guessing wrongly.
- **Out-of-corpus question**: The question concerns a text not yet in the corpus (e.g. a
  Talmudic sugya before Talmud is added) — the system states the source is not in its
  current library rather than fabricating.
- **Mixed-language question**: A question contains both Hebrew and English — the system
  still retrieves correctly and answers in the dominant/requested language.
- **No relevant source**: Retrieval returns nothing sufficiently relevant — the system
  returns an honest "no grounded source found" state, never a fabricated answer.
- **Conflicting sources**: Sources genuinely disagree — the system presents the
  disagreement with attributions instead of silently picking one.
- **Sensitive halachic edge**: A halachic question touches life-impacting matters — the
  caveat and deference to a rav are presented prominently.
- **Long/complex source**: A retrieved source is very long — the system grounds its answer
  in the relevant portion and still cites the full source.

## Requirements *(mandatory)*

### Functional Requirements

**Grounding & trust (core)**

- **FR-001**: System MUST build every answer only from sources retrieved for that
  question, and MUST attach a verifiable citation (reference + link back to the source) to
  each claim.
- **FR-002**: System MUST NOT fabricate sources, citations, attributions, or content not
  present in retrieved material.
- **FR-003**: System MUST return an explicit, honest "no grounded source found" response
  when retrieval yields nothing sufficiently relevant.
- **FR-004**: System MUST attribute each cited statement to the correct source/commentator.

**Capabilities**

- **FR-005**: Users MUST be able to ask a free-form question and receive a grounded, cited
  answer (User Story 1).
- **FR-006**: Users MUST be able to request an explanation of a specific commentator's
  view on a given text (User Story 2).
- **FR-007**: Users MUST be able to request a comparison of multiple commentators on a
  given text, with disagreements surfaced and attributed (User Story 2).
- **FR-007a**: System MUST be able to surface **supercommentaries** — sources whose anchor is
  another commentary — so it can present the commentators who *explain a dispute* between two
  commentators (e.g. who discusses the Rashi–Ramban machloket on a verse), each attributed and
  cited. *(Active once such supercommentary texts are loaded; within-Tanakh commentary works
  in the MVP.)*
- **FR-008**: Users MUST be able to request a structured lesson/shiur on a topic or
  parasha, returned as sources + structure + discussion points, all cited (User Story 3).
- **FR-008a**: A lesson MUST be able to span **multiple corpora** — following the chain of
  transmission from a pasuk to the Rishonim, Acharonim, and the Halacha derived from it —
  drawing on every corpus currently loaded, with each step cited. *(In the Tanakh MVP this
  spans pesukim and their commentators; the full Torah→Halacha chain activates as those
  corpora are loaded.)*
- **FR-009**: Users MUST be able to ask halachic questions and receive sourced guidance
  that surfaces disagreement and ALWAYS includes the "not a substitute for a rav / not a
  binding pesak" caveat (User Story 4). *(Deferred to post-MVP: active only once a halachic
  corpus is added; not part of the Tanakh-first MVP.)*

**Bilingual**

- **FR-010**: System MUST accept questions in Hebrew and in English and answer in the
  language of the question.
- **FR-011**: System MUST retrieve the correct underlying source regardless of whether the
  question is in Hebrew or English (a Hebrew question and its English equivalent reach the
  same source).
- **FR-012**: System MUST quote the Hebrew source text and render Hebrew correctly
  (right-to-left), treating Hebrew as a first-class language throughout.

**Corpus & extensibility**

- **FR-013**: System MUST ship with all of Tanakh plus classical commentators as the
  initial corpus.
- **FR-014**: System MUST allow adding new texts, new commentators, or an entirely new
  body of work (e.g. Gemara, Halacha, Emunah) as a data/configuration operation, without
  changing retrieval, ranking, explanation, or generation behavior.
- **FR-015**: System MUST support incremental additions and re-indexing of the corpus
  without rebuilding the entire index from scratch.
- **FR-016**: Corpus construction MUST be reproducible from documented, scripted steps
  (no undocumented manual steps in the critical path).
- **FR-016a**: System MUST capture and use **explicit cross-references between texts** (the
  source's Links graph, plus commentary→anchor chains) so it can follow the chain of
  transmission — pasuk ↔ its commentaries ↔ supercommentaries, and across corpora to
  Acharonim/Halacha — rather than relying on semantic similarity alone. Each added corpus
  brings its cross-references with it (data/config).

**Deployment profiles**

- **FR-017**: System MUST run fully offline on a personal machine (no internet required at
  query time), using a pre-downloaded corpus. The target offline machine is a **modest
  laptop: CPU-only at query time, ~16GB RAM, no dedicated/required GPU**; the offline
  profile MUST remain interactive within that envelope.
- **FR-018**: System MUST also run as a scalable, multi-user product, with the difference
  between offline and product profiles being configuration only — not separate code paths.
- **FR-019**: A change MUST NOT break one deployment profile while serving the other.

**Interface**

- **FR-020**: System MUST provide a conversational (chat) interface where a learner asks,
  receives a cited answer, and can continue asking follow-up questions that use the context
  of the current conversation. Context retention is **in-session only** for the MVP — the
  system need not persist conversation history across sessions.
- **FR-021**: System MUST present citations as clickable/verifiable links to the source.
- **FR-022**: System MUST be designed to also support, in a later phase, a structured study
  interface (browse a chapter/verse and see sources + explanations alongside the text)
  without re-architecting the core.

**Trustworthiness measurement**

- **FR-023**: System MUST provide an automated evaluation that measures retrieval quality
  and answer grounding against a versioned evaluation set of **at least 100 Tanakh
  questions with expected sources**, designed to grow over time.
- **FR-024**: System MUST allow a change to be checked against the evaluation so that a
  regression in grounding/retrieval can be detected before it is accepted.

**Privacy**

- **FR-025**: In the offline profile, the learner's questions and study data MUST remain on
  the learner's machine.
- **FR-026**: In the product profile, handling of user data MUST be explicit and limited to
  what the service requires.

### Key Entities *(include if feature involves data)*

- **Source Text**: A unit of sacred text (e.g. a verse) with its canonical reference,
  Hebrew text, English translation where available, and its position in the bookshelf
  (work → book → chapter → verse).
- **Commentary**: A commentator's remark tied to a specific Source Text, carrying the
  commentator's identity, its Hebrew text, translation where available, and a reference
  back to the text it comments on.
- **Commentator**: A classical author (Rashi, Ramban, Ibn Ezra, Radak, Sforno, Malbim,
  etc.) whose commentaries are attributed and distinguished. Includes **supercommentators**
  (e.g. Mizrachi, Gur Aryeh, Sifsei Chachamim) whose work comments on another commentary.
- **Cross-reference (Link)**: An explicit, curated connection between two texts (e.g. a pasuk
  and a halacha derived from it, or a verse and a commentary), used to follow the chain of
  transmission across corpora rather than inferring it from similarity.
- **Corpus / Work**: A body of texts (Tanakh today; Gemara, Halacha, Emunah later) that can
  be added as a unit; carries metadata about its scope and source/licensing.
- **Citation**: The link between a claim in an answer and the specific Source Text or
  Commentary it is grounded in, resolvable back to the original.
- **Question / Conversation**: A learner's query (with language and intent — Q&A, explain,
  lesson, halacha) and, in chat, the surrounding context of prior turns.
- **Lesson Plan**: A structured study output — selected sources, a suggested structure, and
  discussion points — each element tied to citations.
- **Evaluation Set**: A versioned collection of questions (100+ at the start, growing)
  paired with expected sources/grounding checks, used to measure trustworthiness.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In at least 95% of grounded-answer responses on the evaluation set, every
  claim is backed by a citation that resolves to a real, relevant source (no fabricated or
  broken citations).
- **SC-002**: For 100% of questions whose answer is absent from the corpus, the system
  returns an honest "no grounded source found" response instead of a fabricated answer.
- **SC-003**: Equivalent Hebrew and English versions of the same question retrieve the same
  underlying source in at least 90% of evaluation pairs.
- **SC-004**: A learner receives a cited answer to a typical question within a few seconds
  in the offline profile on the target machine (a modest CPU-only laptop with ~16GB RAM, no
  GPU) — interactive, not batch.
- **SC-005**: Adding a new commentator or a new body of work to the corpus requires no
  change to retrieval, ranking, explanation, or generation behavior — verified by adding
  one new source as a data/config-only operation.
- **SC-006**: The same release runs in both the offline profile and the product profile
  with only configuration differing, verified by running the same evaluation in both.
- **SC-007**: Every halachic response in the evaluation set includes the "not a substitute
  for a rav / not a binding pesak" caveat (100%) and surfaces disagreement where the
  evaluation expects it.
- **SC-008**: A change that lowers the measured grounding/retrieval score is detectable via
  the evaluation before acceptance (the score is reproducible and comparable across runs).

## Assumptions

- Source texts are drawn from open, free sources (e.g. Sefaria); their licensing and
  attribution are respected and documented.
- The MVP goes deep on **Tanakh** and delivers **User Stories 1–3** (grounded Q&A, explain
  commentators, lesson prep) at high quality. **User Story 4 (halachic guidance) is deferred
  until a halachic corpus is added**, since grounded halachic answers require halachic
  sources (Principle I). Later corpora reuse the same architecture.
- The initial primary interface is **chat**; the structured study interface is a planned
  later phase, and the core is designed not to require re-architecture to add it.
- "High quality" for an answer means: grounded, correctly attributed, in the right
  language, and verifiable — judged against the evaluation set rather than subjective feel.
- The offline profile targets a single **modest laptop (CPU-only at query time, ~16GB RAM,
  no GPU)**; the product profile targets multiple concurrent users on scalable
  infrastructure.
- Conversation context is **in-session only** in the MVP; cross-session history persistence
  is out of scope for now.
- The initial trustworthiness evaluation set contains **100+ Tanakh questions** with
  expected sources and grows over time.
- **Cross-corpus chains and supercommentary** (link-based retrieval, anchor chains) are
  designed in from the start, but the content that fills them — supercommentaries and
  halachic/Acharonim works — is added later via the corpus registry; the Tanakh MVP exercises
  the within-Tanakh version (pesukim ↔ their commentators).
- The author is the initial user and arbiter of quality; product end-users are a future
  audience whose needs are anticipated but not yet gathered in detail.
- This work is governed by the project Constitution v1.1.0; Principle I (Grounded, Never
  Invented) is non-negotiable and Principle VIII (Halachic Humility & Deference) governs
  all halachic responses.
