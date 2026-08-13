# Configuration Reference

Every knob in Chavruta.AI is an environment variable. No code changes are required to adjust any setting – all configuration is resolved from the environment at startup. The retrieval-side configuration is centralized in `src/chavruta/config/profile.py`, which reads `CHAVRUTA_*` variables and constructs a `Profile` object that selects every backend.

## Profile & deployment

| Variable | Purpose | Default | Where read |
|----------|---------|---------|------------|
| `CHAVRUTA_PROFILE` | Selects the preset configuration: `local` (personal machine) or `cloud` (scalable product) | `local` | `src/chavruta/config/profile.py:89` |

## Vector store / corpus

| Variable | Purpose | Default | Where read |
|----------|---------|---------|------------|
| `CHAVRUTA_QDRANT_MODE` | Qdrant deployment mode: `embedded` (in-process) or `server` (remote/ Docker) | `embedded` | `src/chavruta/config/profile.py:95` |
| `CHAVRUTA_QDRANT_PATH` | Storage path for embedded Qdrant (data directory) | `BASE_DIR/data/qdrant` | `src/chavruta/config/profile.py:96` |
| `CHAVRUTA_QDRANT_URL` | Qdrant server URL (for `server` mode) | `""` | `src/chavruta/config/profile.py:97` |
| `CHAVRUTA_QDRANT_API_KEY` | Qdrant Cloud API key (for remote server) | `""` | `src/chavruta/config/profile.py:98` |
| `CHAVRUTA_COLLECTION` | Qdrant collection name (the live production collection is `chavruta_commercial`) | `chavruta_commercial` | `src/chavruta/config/profile.py:99` |
| `CHAVRUTA_MEM_TIER` | RAM budget for the index: `ssd` (memmapped, ~1–2GB), `16gb`, `32gb`, or `max` | `ssd` | `src/chavruta/config/profile.py:100` |
| `CHAVRUTA_TEMPLATES_COLLECTION` | Collection name for the lesson-template RAG | `chavruta_templates` | `app/api.py:251` |

## Embedding & retrieval

| Variable | Purpose | Default | Where read |
|----------|---------|---------|------------|
| `CHAVRUTA_EMBEDDING_MODEL` | HuggingFace model ID for embeddings | `BAAI/bge-m3` | `src/chavruta/config/profile.py:93` |
| `CHAVRUTA_EMBEDDING_DEVICE` | Device for embedding model: `cpu` or `cuda` | `cpu` | `src/chavruta/config/profile.py:94` |
| `CHAVRUTA_TOP_K` | Number of sources to retrieve per query | `8` | `src/chavruta/config/profile.py:101` |
| `CHAVRUTA_HYBRID` | Enable hybrid retrieval (dense + sparse via RRF) | `True` | `src/chavruta/config/profile.py:102` |
| `CHAVRUTA_RERANK` | Enable cross-encoder reranking (GPU-only in practice) | `False` | `src/chavruta/config/profile.py:103` |
| `CHAVRUTA_RERANK_MODEL` | Model ID for the reranker | `BAAI/bge-reranker-v2-m3` | `src/chavruta/config/profile.py:104` |
| `CHAVRUTA_RELEVANCE_THRESHOLD` | Minimum dense cosine similarity for a source to be considered "relevant" | `0.5` | `src/chavruta/config/profile.py:105` |
| `CHAVRUTA_LINKS_PATH` | Path to the link graph JSONL file (built by `scripts/build_links.py`) | `data/links.jsonl` | `scripts/build_links.py:27` |

## Generation / LLM

| Variable | Purpose | Default | Where read |
|----------|---------|---------|------------|
| `CHAVRUTA_LLM_BACKEND` | LLM backend: `nebius` (the Nebius API, default) or `bridge` (Claude in-session, no external API) | `nebius` | `src/chavruta/config/profile.py:106` |
| `CHAVRUTA_LLM_MODEL` | Model ID for the LLM | `Qwen/Qwen3-235B-A22B-Instruct-2507` | `src/chavruta/config/profile.py:107` |
| `CHAVRUTA_LLM_BASE_URL` | Base URL for the LLM API | `https://api.studio.nebius.ai/v1` | `src/chavruta/config/profile.py:108` |
| `CHAVRUTA_LLM_API_KEY` | API key for the LLM provider (also accepts `NEBIUS_API_KEY` as a fallback) | `""` | `src/chavruta/config/profile.py:109` |
| `CHAVRUTA_LLM_TEMPERATURE` | Sampling temperature for generation | `0.2` | `src/chavruta/config/profile.py:110` |
| `CHAVRUTA_LLM_MAX_TOKENS` | Maximum tokens per LLM call (per-intent caps in the pipeline override this) | `512` | `src/chavruta/config/profile.py:111` |
| `CHAVRUTA_LLM_TIMEOUT_S` | Per-call timeout in seconds (bounds agentic loop duration) | `180.0` | `src/chavruta/config/profile.py:112` |
| `CHAVRUTA_LLM_MAX_RETRIES` | Maximum retries per LLM call | `1` | `src/chavruta/config/profile.py:113` |
| `CHAVRUTA_QUERY_PLANNER` | Query planning mode: `none` (heuristic only) or `llm` (LLM fallback) | `none` | `src/chavruta/config/profile.py:114` |
| `CHAVRUTA_BRIDGE_DIR` | Directory for bridge-mode file handshake (pending/ and answers/ subdirs) | `data/llm_bridge` | `src/chavruta/llm/bridge.py:34` |
| `CHAVRUTA_BRIDGE_MAX_ROUNDS` | Maximum agentic retrieval rounds in bridge mode | `4` | `src/chavruta/llm/agentic.py:22` |
| `CHAVRUTA_LLM_BREAKER_FAILS` | Consecutive failures before the circuit breaker opens | `5` | `src/chavruta/llm/cloud.py:63` |
| `CHAVRUTA_LLM_BREAKER_COOLDOWN_S` | Circuit breaker cooldown duration in seconds | `30` | `src/chavruta/llm/cloud.py:64` |

## Security & serving

⚠️ **Critical for production deployments** – these variables control authentication, rate limiting, and request validation. Left at their defaults in a public deployment, the API would be open to abuse.

| Variable | Purpose | Default | Where read | Production risk if left at default |
|----------|---------|---------|------------|-----------------------------------|
| `CHAVRUTA_API_KEYS` | Comma-separated list of allowed API keys (empty = disabled) | `""` | `app/security.py:41` | **No authentication** – anyone can call the API |
| `CHAVRUTA_CORS_ORIGINS` | Comma-separated list of allowed CORS origins (browser policy) | `http://localhost:5173,http://localhost:4173` | `app/api.py:186` | **Blocks legitimate requests** from your production domain |
| `CHAVRUTA_RATE_PER_MIN` | Requests per minute per IP (rate limiting) | `20` | `app/security.py:160` | **Too permissive** – allows abuse of expensive LLM calls |
| `CHAVRUTA_RATE_PER_HOUR` | Requests per hour per IP (rate limiting) | `200` | `app/security.py:161` | **Too permissive** – allows sustained abuse |
| `CHAVRUTA_TRUSTED_PROXY_HOPS` | Number of trusted reverse proxies in front of the app (for X-Forwarded-For parsing) | `0` | `app/security.py:176` | **IP spoofing** – attackers can rotate X-Forwarded-For to bypass rate limits |
| `CHAVRUTA_MAX_BODY_BYTES` | Maximum request body size in bytes | `2,097,152` (2 MB) | `app/security.py:223` | **DoS risk** – large bodies can exhaust memory |
| `CHAVRUTA_PUBLIC_HEALTH_DETAILS` | If non-empty, expose internal details in `/health` endpoint | `""` | `app/api.py:935` | **Information disclosure** – leaks internal state |

## Admin dashboard & error tracking

Both optional; unset means off. `CHAVRUTA_ADMIN_OWNERS` is a dedicated allowlist — separate from
`CHAVRUTA_CALENDAR_BETA_OWNERS` even when it names the same account, and with no `"*"` wildcard
(admin access should never mean "everyone").

| Variable | Purpose | Default | Where read |
|----------|---------|---------|------------|
| `CHAVRUTA_ADMIN_OWNERS` | Comma-separated Supabase owner_ids allowed to see `/admin` | `""` (nobody) | `app/api.py::_is_admin` |
| `SENTRY_DSN` | Backend error tracking (sentry.io, free tier) — sign up, create a Python/FastAPI project, paste its DSN | `""` (off) | `app/api.py::_configure_sentry` |

## Email sending (Resend)

Optional; unset means off. Used for operator-initiated broadcasts (e.g. policy updates), not auth/transactional emails (those go through Supabase). Recipients are sent via BCC for privacy — no recipient sees another recipient's address. The module follows the project's "no value = inert" convention: if not configured, `send_email()` returns `False` and logs a warning rather than raising an exception.

| Variable | Purpose | Default | Where read |
|----------|---------|---------|------------|
| `RESEND_API_KEY` | Resend API key — get one at https://resend.com (free tier: 100 emails/day) | `""` (off) | `app/email.py` |
| `RESEND_FROM` | Sender email address — use `@resend.dev` for initial testing without a verified domain | `""` (off) | `app/email.py` |

## Plans, quotas & billing

These variables override the default subscription tiers and credit costs defined in `app/plans.py`. The tier IDs are: `free`, `basic`, `pro`, `institution`.

### Tier-specific quotas (per-tier patterns)

| Pattern | Purpose | Default | Where read |
|---------|---------|---------|------------|
| `CHAVRUTA_TOKENS_DAY_<TIER>` | Daily conversation token quota for the tier (0 = uncapped) | Tier defaults in `app/plans.py` | `app/plans.py:150` |
| `CHAVRUTA_TOKENS_WEEK_<TIER>` | Weekly conversation token quota for the tier (0 = uncapped) | Tier defaults in `app/plans.py` | `app/plans.py:161` |
| `CHAVRUTA_LESSONS_WEEK_<TIER>` | Weekly lesson count quota for the tier (0 = uncapped) | Tier defaults in `app/plans.py` | `app/plans.py:170` |
| `CHAVRUTA_PRICE_<TIER>` | Monthly price in ILS for the tier | Tier defaults in `app/plans.py` | `app/plans.py:212` |
| `CHAVRUTA_ANNUAL_PRICE_<TIER>` | Annual price in ILS for the tier | Tier defaults in `app/plans.py` | `app/plans.py:207` |

### Subscription & billing

| Variable | Purpose | Default | Where read |
|----------|---------|---------|------------|
| `CHAVRUTA_SUB_PERIOD_DAYS` | Days of access a monthly subscription buys | `30` | `app/plans.py:200` |
| `CHAVRUTA_ANNUAL_PERIOD_DAYS` | Days of access an annual subscription buys | `365` | `app/plans.py:199` |
| `CHAVRUTA_SUB_PRICE_ILS` | Legacy single-price knob (pro tier monthly, superseded by tier-specific prices) | `49.9` | `app/plans.py:214` |
| `CHAVRUTA_SUB_DESCRIPTION` | Invoice line description (empty = auto-generated Hebrew description) | `""` | `app/billing/service.py:30` |
| `CHAVRUTA_BILLING_SWEEP_INTERVAL_S` | Interval for the billing downgrade sweeper (seconds) | `3600` | `app/billing/service.py:155` |
| `CHAVRUTA_PUBLIC_URL` | Public base URL for payment provider callbacks | `http://localhost:5173` | `app/billing/payplus.py:55` |

### Credits & coupons

| Variable | Purpose | Default | Where read |
|----------|---------|---------|------------|
| `CHAVRUTA_CREDIT_COSTS` | Per-intent credit costs (format: `lesson=5,halacha=2`; empty = 1 for all) | Defaults in `app/plans.py` | `app/plans.py:237` |
| `CHAVRUTA_TOKEN_ESTIMATE_<INTENT>` | Normalized tokens to reserve before a generation of this intent | Intent-specific defaults | `app/plans.py:183` |
| `CHAVRUTA_COUPON_ATTEMPTS_PER_HOUR` | Max coupon redemption attempts per account per hour | `10` | `app/coupons.py:95` |

## Data lifecycle

| Variable | Purpose | Default | Where read |
|----------|---------|---------|------------|
| `CHAVRUTA_CHAT_RETENTION_DAYS` | Days to keep chats after last activity (0 = keep forever) | `90` | `app/accounts.py:118` |
| `CHAVRUTA_ACCOUNT_DELETION_GRACE_DAYS` | Grace period before a scheduled account deletion is executed | `30` | `app/accounts.py:29` |
| `CHAVRUTA_DELETION_SWEEP_INTERVAL_S` | Interval for the account deletion sweeper (seconds) | `3600` | `app/accounts.py:147` |

## Local / misc

| Variable | Purpose | Default | Where read |
|----------|---------|---------|------------|
| `CHAVRUTA_DB_PATH` | Path to the SQLite chat-history database | `repo-root/chavruta.db` | `app/db.py:20` |
| `CHAVRUTA_LOG_LEVEL` | Logging level for the chavruta.* loggers | `INFO` | `app/api.py:87` |
| `CHAVRUTA_TZ` | Timezone for datetime operations | `Asia/Jerusalem` | `app/api.py:1220` |
| `CHAVRUTA_SEED_DEMO` | If `1`, seed showcase conversations into a brand-new database | `0` | `app/db.py:373` |

## Switching the model

The API backend is a plain OpenAI-compatible client, so the provider is a base URL, a model id and a
key — changing it is configuration, never code. `CHAVRUTA_LLM_BACKEND` accepts `api` (or `openai`, or
the historical `nebius`) for any such provider, and `bridge` for the no-API path.

| Variable | Meaning |
|---|---|
| `CHAVRUTA_LLM_PRESET` | A named provider from `src/chavruta/llm/presets.py` — fills in base URL, model and output floor. Explicit variables below always win. |
| `CHAVRUTA_LLM_BASE_URL` / `CHAVRUTA_LLM_MODEL` / `CHAVRUTA_LLM_API_KEY` | The provider, spelled out. |
| `CHAVRUTA_LLM_MIN_OUTPUT_TOKENS` | A floor under every per-call output budget. `0` (default) for a model that answers directly. |

**The floor exists for reasoning models, and it is not optional on them.** A model that thinks before
it answers can spend an entire output allowance on `reasoning_content` and return HTTP 200 with an
empty answer. The per-intent budgets in `pipeline.py` (a question gets 3,000 tokens) were sized for a
model that answers directly, so on a reasoning model every short answer comes back empty. Measured on
Macaron V1 Venti on 2026-07-27: ~86,000 characters of reasoning and no answer at 24,000 tokens;
normal completion at 96,000. That case now raises `LLMEmptyAnswerError` naming the variable to raise,
instead of returning `""` and being misdiagnosed downstream as a retrieval failure.

**The baseline is `nebius` / `Qwen/Qwen3-235B-A22B-Instruct-2507`.** Every quality figure we have —
the eval, citation behaviour, the Hebrew-only rule, `_strip_foreign` — was measured on it. Any other
model is unmeasured until the eval is run against it.

## Notes

- The `NEBIUS_API_KEY` environment variable is accepted as a fallback for `CHAVRUTA_LLM_API_KEY` for convenience.
- Several PayPlus-specific variables (`PAYPLUS_MODE`, `PAYPLUS_API_KEY`, `PAYPLUS_SECRET_KEY`, `PAYPLUS_PAYMENT_PAGE_UID`, `PAYPLUS_ANNUAL_RECURRING_TYPE`, `PAYPLUS_REFUND_PATH`) are used by `app/billing/payplus.py` but are not prefixed with `CHAVRUTA_` because they are provider-specific.
- `PAYPLUS_REFUND_PATH` (default `Transactions/RefundByTransactionUID`) and `CHAVRUTA_INVOICE_CREDIT_TYPE` (default `330`, חשבונית זיכוי) exist because neither call has been exercised against a live account. They are escape hatches for the first real refund, not knobs to tune — see `scripts/refund.py`.
- Supabase-specific variables (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`) are used by `app/auth_supabase.py` for authentication and are not prefixed with `CHAVRUTA_` because they are provider-specific.
- Resend-specific variables (`RESEND_API_KEY`, `RESEND_FROM`) are used by `app/email.py` for operator broadcasts and are not prefixed with `CHAVRUTA_` because they are provider-specific.
