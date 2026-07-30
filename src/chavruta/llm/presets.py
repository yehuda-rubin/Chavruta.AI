"""Named provider presets — so changing the model is one environment variable, not four.

Every serverless provider worth using speaks the OpenAI chat-completions shape, which means the
backend never needed to know whose model it is: `CloudLLM` takes a base URL, a model id and a key,
and that is the whole difference between providers. What was missing was somewhere to keep the
combinations, so switching meant looking up a base URL and getting it subtly wrong.

    CHAVRUTA_LLM_PRESET=nebius          # the default; explicit env vars still win

A preset only fills in what the environment has not already set, so any single field stays
overridable — a preset is a starting point, never a lock.

`min_output_tokens` is here because it is a property of the MODEL, not of a deployment. A model that
reasons before it answers can spend a whole output allowance on thinking and return an empty answer
(see cloud.LLMEmptyAnswerError); the per-intent budgets in the pipeline — 3,000 tokens for a
question — were sized for models that answer directly. Recording the floor beside the model is what
stops that from being rediscovered as a mysterious empty response every time someone switches.

Adding one is deliberately trivial: a row here, no code. What a row must NOT carry is an API key.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    base_url: str
    model: str
    min_output_tokens: int = 0
    note: str = ""


PRESETS: dict[str, Preset] = {
    # The validated baseline. Every quality number we have — the eval, the citation behaviour, the
    # Hebrew-only rule, _strip_foreign — was measured against this model. Treat it as the control.
    "nebius": Preset(
        "https://api.studio.nebius.ai/v1",
        "Qwen/Qwen3-235B-A22B-Instruct-2507",
        note="baseline: every quality measurement we have was taken here",
    ),
    # Novita serves several large models on an OpenAI-compatible endpoint.
    "novita": Preset(
        "https://api.novita.ai/v3/openai",
        "qwen/qwen3-235b-a22b-instruct-2507",
        note="same model family as the baseline, different host",
    ),
    # Macaron V1 Venti — 748B (GLM-5.2 base + LoRA specialists), 1M context, 128k max output.
    # A REASONING model: measured 2026-07-27 returning ~86,000 characters of reasoning and an empty
    # answer at a 24,000-token budget, and completing normally at 96,000. Hence the floor, which is
    # large because the observation was.
    "macaron": Preset(
        "https://api.novita.ai/v3/openai",
        "mindai/macaron-v1-venti",
        min_output_tokens=32_000,
        note="reasoning model: thinks at length before answering; needs a large output floor",
    ),
    # Tencent Hunyuan Hy3 — 295B total / 21B active MoE, 256K context, 262K max output. The closest
    # architectural match to the baseline we have found (235B/21-22B active), which is the reason to
    # take it seriously: same compute class, so the eval has a fair chance of transferring. It is a
    # reasoning model with selectable modes, hence the floor; if a mode that answers directly is
    # available, set CHAVRUTA_LLM_MIN_OUTPUT_TOKENS=0 for it and the floor costs nothing.
    "hy3": Preset(
        "https://api.novita.ai/v3/openai",
        "tencent/hy3",
        min_output_tokens=8_000,
        note="295B/21B active MoE — same class as the baseline; reasoning modes; cache read priced "
             "at a quarter of input, which suits our large stable prompt prefix",
    ),
    # Cloudflare Workers AI. Its ceiling is around the 70B class — smaller than the baseline.
    "cloudflare": Preset(
        "https://api.cloudflare.com/client/v4/accounts/ACCOUNT_ID/ai/v1",
        "@cf/qwen/qwen3-30b-a3b-fp8",
        note="cheapest of the candidates; replace ACCOUNT_ID; models top out near the 70B class",
    ),
    # Google Gemini, via its OpenAI-compatible endpoint. Pro was REMOVED from the free tier entirely
    # (verified 2026-07-29, ai.google.dev/gemini-api/docs/pricing) — Flash and Flash-Lite are what's
    # actually free, at a tight quota (~10-15 RPM / a few hundred RPD, tightened further Dec 2025).
    # Flash is a "thinking" model by default; the floor below is an untested-but-safe guess against
    # the same empty-answer failure mode as macaron/hy3 above — tighten CHAVRUTA_LLM_MIN_OUTPUT_TOKENS
    # down once measured live. Not yet run against the eval — treat as unvalidated vs. the baseline.
    "gemini": Preset(
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "gemini-2.5-flash",
        min_output_tokens=8_000,
        note="free-tier model (Pro is NOT free); unpaid tier trains on input AND is read by human "
             "reviewers per Google's ToS — enable billing on the Google Cloud project behind this "
             "key (or swap in a key from a billing-enabled project) the moment there is a first "
             "paying customer, not before",
    ),
}


def resolve(name: str | None) -> Preset | None:
    """The preset for a name, or None. Unknown names return None rather than raising: a preset is a
    convenience, and a typo in one should not take the service down when the explicit environment
    variables beside it are perfectly sufficient to run."""
    return PRESETS.get((name or "").strip().lower()) or None


def names() -> list[str]:
    return sorted(PRESETS)
