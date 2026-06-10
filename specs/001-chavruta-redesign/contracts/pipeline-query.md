# Contract: Pipeline (query → grounded answer)

The top-level contract the UI/CLI call. Orchestrates intent → retrieve → generate → cite,
and is the single place grounding is enforced. Same call in both profiles.

## Interface

```python
class ChavrutaPipeline:
    def __init__(self, profile: Profile): ...     # builds backends from config

    def ask(self, request: AskRequest) -> AskResponse: ...
    def ask_stream(self, request: AskRequest) -> Iterator[AskEvent]: ...

class AskRequest:
    text: str
    lang: str | None = None            # auto-detected if None
    intent: str | None = None          # auto-routed if None: qa | explain | lesson
    work_ids: list[str] | None = None  # default: all indexed works
    history: list[Turn] = []           # in-session only

class AskResponse:
    answer: str                        # in the question's language
    citations: list[Citation]          # each resolves to a retrieved chunk
    grounded: bool
    no_source: bool                    # True → honest empty state, answer explains this
    caveats: list[str]                 # e.g. halachic caveat (reserved, post-MVP)
    intent: str
    lesson_plan: LessonPlan | None     # populated when intent == lesson
```

## Contract rules (the grounding gate — Principle I)

- Every sentence asserting Torah content in `answer` MUST map to ≥1 `citation` that resolves
  to a chunk actually returned by the Retriever for this request. Unmapped claims are a
  contract violation.
- If retrieval `is_empty`, the pipeline MUST return `no_source = True` with an honest message
  and MUST NOT fabricate content or citations (FR-002/003).
- `answer` language MUST match the question language (FR-010).
- For `intent == explain`, positions MUST be attributed to the correct commentator; for a
  comparison, disagreements MUST be surfaced, not flattened (FR-006/007).
- For `intent == lesson`, `lesson_plan` sections MUST each carry resolving citations (FR-008).
- `intent == halacha` is **reserved/deferred** (no halachic corpus in MVP); when enabled it
  MUST always attach the "not a substitute for a rav / not a binding pesak" caveat
  (Principle VIII).
- Behavior MUST be identical across profiles except quality/latency (Principle II).

## Conformance tests (tests/integration)

- Grounded-answer happy path: known question → answer with resolving citations, `grounded`.
- No-source path: out-of-corpus question → `no_source = True`, no fabricated citation.
- Bilingual: HE and EN forms of one question → same sources, answer in each language.
- Profile parity: same request on `local` and `cloud` profiles yields citations to the same
  sources (SC-006).
- Eval gate: running the harness through `ask` meets SC-001/SC-002/SC-007 thresholds.
