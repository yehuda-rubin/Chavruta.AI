# Contract: LLMBackend

Generates the natural-language answer from an already-built, source-grounded prompt. The
dual-model strategy lives here: `LocalLLM` (DictaLM via Ollama/llama.cpp) and `CloudLLM`
(Nebius, OpenAI-compatible) implement the same interface, chosen by config (Principle II).

## Interface

```python
class LLMBackend(Protocol):
    model_id: str
    profile: str                  # "local" | "cloud"

    def generate(self, prompt: GroundedPrompt, *, lang: str,
                 max_tokens: int, temperature: float) -> LLMResult: ...
    def stream(self, prompt: GroundedPrompt, **kw) -> Iterator[str]: ...   # for responsive UX

class GroundedPrompt:
    system: str                   # grounding + citation + language rules
    sources: list[SourceBlock]    # the ONLY knowledge the model may use
    question: str
    history: list[Turn]           # in-session context only

class LLMResult:
    text: str
    finish_reason: str
```

## Contract rules

- The backend MUST be given the retrieved `sources` and MUST be instructed (system prompt)
  to answer **only** from them and to cite them — grounding is enforced by the pipeline, not
  trusted to the model alone (Principle I).
- The backend MUST NOT fetch external knowledge or tools at generate time in the local
  profile (offline, FR-017).
- MUST answer in `lang` (the question's language) (FR-010/IV).
- `LocalLLM` MUST operate within the offline RAM/latency budget (DictaLM Q4 ~4.4GB).
- Swapping `LocalLLM` ↔ `CloudLLM` MUST require config only — identical call site.
- Streaming SHOULD be supported for responsive UX (Principle VII).

## Conformance tests (tests/contract)

- Given a prompt whose sources do not contain the answer, the backend's output (after
  pipeline enforcement) resolves to the honest "no grounded source" path (FR-003).
- A Hebrew question yields a Hebrew answer; English → English (FR-010).
- Local and cloud backends are interchangeable behind the same `generate` signature
  (profile parity).
