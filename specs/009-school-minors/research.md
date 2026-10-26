# Research: School-Track Minors Support

Background (legal, industry, code audit): [docs/MINORS_READINESS.md](../../docs/MINORS_READINESS.md).
This file records the technical decisions that the plan depends on.

## R1. Where the age record lives

- **Decision**: store it in a new SQLite table, `age_records`, in `chavruta.db`, keyed by `owner_id`. It is
  written only by backend endpoints. Supabase `user_metadata` is never trusted for it.
- **Rationale**:
  - `user_metadata` can be written by the account holder with the public anon key, through
    `supabase.auth.updateUser` (`web/lib/auth.tsx:100`). Storing age there would make FR-003 false.
  - `specs/004-school-accounts/plan.md` ("The under-18 flag") already showed that two gates cannot read JWT
    metadata at all. `db.reviewable_questions` is pure SQL, and the retention sweeper is a background thread.
    A metadata flag would make both of them fail **open**.
- **Alternatives considered**:
  - Supabase `app_metadata`, which only the service role can write. It is secure, but SQL gates still
    cannot see it.
  - A column on `accounts`. This was rejected because `accounts` rows are created lazily and their meaning
    is billing, while age is identity.

## R2. "Written as minor" per message

- **Decision**: add an immutable column `messages.minor_until`. It holds the deletion date for a message
  written as a minor, and is NULL for adults. It is set inside `save_message` from the author's age record
  at write time. `saved_lessons` and `saved_source_sheets` get the same column.
- **Rationale**:
  - A deletion date covers both "is minor" and "when to delete" in one column.
  - Review and retention filter on `minor_until IS NULL` or `minor_until <= now`.
  - Setting the date at write time makes FR-024 and FR-031 hold automatically after the author turns 18.
- **Alternatives considered**:
  - A boolean plus a computed date. That is two sources of truth.
  - Per-session marking. A session can span the 18th birthday (FR-031).

## R3. Signup: birth month/year replaces the 18+ checkbox

- **Decision**:
  - At signup the client sends the birth month and year to a new backend endpoint, `POST /account/age`,
    on the first authenticated call.
  - The endpoint accepts the value only when no record exists yet. After that, only the parent or the
    operator endpoints can change it.
  - `require_auth` keeps accepting `age_confirmed_18` for existing accounts (FR-007b).
  - A new account without an age record gets `403 age_required`. `/me` and `/account/*` remain exempt.
- **Rationale**:
  - The signup form cannot write to SQLite before the account exists. Writing on first use, once only,
    keeps the trust boundary on the server.
  - A minor who lies at signup is the accepted v1 limit, per the PPA draft guidance (spec Edge Cases).
- **Alternatives considered**:
  - A Supabase signup hook. This adds infrastructure (YAGNI).
  - Asking every existing user for a birth date. This was rejected: they already declared 18+.

## R4. Linking a minor to a school

- **Decision**:
  - **Join link**: reuse the existing `org_invites` codes (`orgs.create_invite` with `max_uses` and expiry,
    and `revoke_invite`). `accept_invite` gains one rule: when the joiner is a minor, the membership row is
    created with `is_minor = 1`. The existing student-code button is not modified (FR-007c). Only the join
    path changes for minors.
  - **By account ID**: add a new table, `org_join_requests`, with columns `org_id`, `owner_id`,
    `requested_by`, `status` and timestamps. The admin creates a request, and the student approves or declines
    it from their account page. Approval reuses the membership insert used by `accept_invite`.
- **Rationale**:
  - The invite system already has caps, expiry, revoke, sticky removal and the one-org-per-account unique
    index (`app/db.py:225`).
  - Adding a second link mechanism would duplicate all of that.
- **Alternatives considered**:
  - A brand-new link type. This duplicates `org_invites`.
  - Auto-joining by account ID without the student's approval. The spec requires approval.

## R5. Parent link

- **Decision**:
  - Add a new table, `parent_links`, with columns `parent_owner_id`, `child_owner_id`, `status` and
    timestamps.
  - The parent must be an adult account, meaning one with an age record of 18 or more, or a legacy 18+
    declaration. The parent requests the link by the child's account ID, and the child approves it.
  - A linked parent can correct the child's age through `PUT /parent/children/{id}/age`. A linked parent can
    also set content switches, through FR-023a.
  - Paying for a child's subscription is out of scope for this feature. That is the founder's "later"
    decision.
- **Rationale**: these are the smallest capabilities that the spec gives parents.

## R6. Crisis screening

- **Decision**: the screening has two stages and runs only for minor accounts, before generation.
  1. **Deterministic phrase layer** in a new `app/crisis.py`. It is a Hebrew and English list with
     inflection-tolerant matching: prefix and suffix stripping, final-letter normalisation, niqqud strip,
     common transliterations. A hit decides the outcome immediately.
  2. **Classifier**: a short call to a small Claude model, with a fixed classification prompt and a JSON
     output of `{category, immediate_danger}`. It runs only when stage 1 did not fire.
  - A transient classifier failure is **fail-safe**: the student gets the normal answer, the turn is logged
    for review as `screen_unavailable`, and the system does not block. It never shows the crisis reply on an
    error.
- **Rationale**:
  - Minors' traffic already goes to Anthropic (R8), so the classifier adds **no new sub-processor**.
  - A self-hosted guard model such as Qwen3Guard needs a GPU, which the production VM does not have, and its
    Hebrew quality is unverified.
  - Generic moderation APIs (OpenAI, Azure) would add a new data recipient and have weak or unknown Hebrew
    support.
- **Open item, verified before release**: classifier recall and false-positive rate on the synthetic sets
  (SC-002, SC-003). If the classifier is too noisy on halachic text, fall back to the phrase layer plus the
  classifier on a narrower trigger set.
- **Alternatives considered**: Qwen3Guard self-hosted (GPU); OpenAI omni-moderation (new processor, Hebrew
  untested); phrase layer only (too low recall, which the research names as the main failure).

## R7. Crisis alert delivery

- **Decision**:
  - Add a new table, `crisis_alerts`, with columns for the student, the org, the category, a
    danger flag, the time and acknowledgement. It never stores message text.
  - Alerts are delivered by email through the existing `app/email_pool.py` to the school's safety contacts,
    a new column on `orgs`, and to the operator (`CHAVRUTA_ADMIN_OWNERS`). They also appear in the
    `/orgs/panel` "alerts" list and the operator's admin page.
  - The email body names the student, the time and the category, with a link. It contains no transcript.
- **Rationale**:
  - Email is the only push channel the stack has. The 5-minute SLA in SC-002 is met by sending
    synchronously in the request path, with retries.
- **Alternatives considered**: SMS or WhatsApp, which would need a new vendor and cost money; panel-only
  alerts, which miss the SLA.

## R8. Minor traffic always goes to Claude API

- **Decision**:
  - Add an `anthropic` preset to `src/chavruta/llm/presets.py`, behind the existing OpenAI-compatible
    `CloudLLM` path if Anthropic's OpenAI-compatible endpoint is adequate, and otherwise behind a thin
    native client.
  - For an owner whose age record is a minor, `api.py` always selects this preset, whatever
    `CHAVRUTA_LLM_BACKEND` is. If the preset is not configured, the minor's request fails closed with
    `503 minor_backend_unavailable`, and the request never falls back to Nebius.
  - Before implementation, verify the API details with the `claude-api` skill.
- **Rationale**:
  - The founder decided that minors' data goes to Claude API.
  - Nebius states its service is not intended for under-18s and keeps inputs for speculative decoding unless
    ZDR is on.
  - A fallback to Nebius would silently break the no-training promise.
- **Alternatives considered**: switching all traffic to Claude. That is a separate product decision, and this
  feature must not depend on it.

## R9. Minor answer rules

- **Decision**:
  - Add one `MINOR_SAFETY_HE` / `MINOR_SAFETY_EN` block in `src/chavruta/generation/grounded.py`. It is appended
    to **every** mode's system prompt when `audience_minor=True`.
  - The block covers Torah scope with a gentle redirect, no graphic detail, no companion or romantic persona,
    and no ruling for practice ("present sources and opinions, refer to your rav or teacher", following
    Principle VIII), plus Anthropic's child-safety text if provided.
  - The "apply principles to modern cases" instruction (`grounded.py:204-211`) is dropped for minors.
  - Retrieved sources are wrapped as untrusted data for everyone in `llm/base.py`, at the same time.
- **Rationale**:
  - One block is less to maintain than per-mode variants.
  - The flag reaches the prompt builder the same way the `audience` field already reaches lesson mode.
- **Alternatives considered**: per-mode prompts, which multiply maintenance; output classification only,
  which comes too late.

## R10. Content denylist on every retrieval path

- **Decision**:
  - Resolve the effective denylist per request, as the union of school-disabled and parent-disabled
    entries. Categories expand to `work_id`s through the library catalogue in `data/search_index.db`.
  - Extend `QdrantStore._build_filter` with a `$not` key that maps to a Qdrant `must_not` `MatchAny` on
    `work_id`.
  - Pass the denylist through `Query`, so that `hybrid._filters`, `_work_filter`, the unscoped fallback
    (`hybrid.py:313-322`), the base and foundational floors (`:397-430`), `fetch_by_refs`, link expansion and
    the agentic `===NEED_SOURCES===` loop all receive it.
  - Add a final **post-filter** in the answer assembly that drops any citation whose `work_id` is denied, as
    defence in depth.
- **Rationale**:
  - The research found several paths that bypass the scope filter, so one choke point is not enough.
  - The post-filter guarantees SC-005 even if a path is missed.
- **Open item**: verify that `search_index.db` book identifiers map 1:1 to corpus `work_id`. If they do not,
  build the category→work_id map with `scripts/` from the corpus itself.
- **Alternatives considered**: a payload backfill of an `audience_ok` field. A backfill runs at about 5
  points per second, which means days, and the denylist is per school anyway.

## R11. Retention, review, marketing and commerce gates

- **Decision**:
  - **Retention**: `run_retention` gains a second pass that deletes messages, lessons and sheets where
    `minor_until <= now`, independent of session activity. The minor retention period is configurable as
    `CHAVRUTA_MINOR_RETENTION_DAYS`, default 60.
  - **Review**: `reviewable_questions` adds `AND m.minor_until IS NULL`. The harvest and training scripts
    read only through it (existing rule).
  - **Marketing**: `marketing.list_marketing_recipients` excludes any `owner_id` with a minor age record.
    `scripts/send_broadcast.py` is pointed at the same consent-and-minor filter.
  - **Commerce**: billing, coupon and referral endpoints refuse minors with
    `403 minor_no_purchase`. The UI hides them, using a `is_minor` field on `/me`.
  - **Admin views**: `list_flagged_messages` and `list_feedback` return the category plus a redacted snippet,
    with no `owner_id`, for minor rows.
- **Rationale**: each of these existing choke points was already identified in the audit.

## R12. Turning 18

- **Decision**:
  - `/me` reports `adult_terms_required` when `adult_from <= today` and no adult acceptance is recorded in
    `age_records.adult_terms_accepted_at`.
  - Message-sending endpoints return `403 adult_terms_required` until the user accepts through
    `POST /account/adult-terms`. That call records the acceptance, and from then on new messages are saved
    with `minor_until = NULL`.
  - Marketing consent remains a separate, optional toggle.
- **Rationale**: this implements FR-030 and FR-031 as the founder specified, with sending blocked until the
  terms are accepted.

## R10 investigation

Task T034. Question: do the book identifiers and `category_path` in `data/search_index.db` map to the corpus
`work_id` that the Qdrant filter sees?

**Answer: no. `work_id` is the tier slug, not a book id, so a `work_id` denylist can only deny a whole tier.**

- **What `work_id` is.** `scripts/build_search_index.py` takes it from the tier file name (`default_work_id=slug`,
  line 246-250) and derives `canon_order` from it with a 15-entry table (`tanakh`, `mishnah`, `tosefta`, `gemara`,
  `yerushalmi`, `midrash`, `halacha`, `shut`, `kabbalah`, `chasidut`, `jewish_thought`, `musar`, `liturgy`,
  `second_temple`, `reference`). The retriever's floors use the same values (`_FOUNDATIONAL_WORKS` in
  `retrieval/hybrid.py`). So `work_id` has 15 values for about 2.5M points.
- **What a book is.** The `chunks` table has separate `book` (title), `author_he` and `category_path` columns
  (`"Chasidut / Breslov"` style, `" / "` separated), next to `work_id`. `category_path` is a Sefaria category
  path, which is finer than a tier (`Halakhah/Mishneh Torah`, `Talmud/Bavli/Seder Moed`), and it does not map to
  `work_id` one to one: Sefaria's top level (`Halakhah`, `Talmud`, `Responsa`) is not the tier list either
  (`Halakhah` feeds `halacha`; `Talmud` feeds `gemara` and `yerushalmi`).
- **Limit of this check.** The local `data/search_index.db` is a 0-byte file on this machine, so the column
  contents could not be sampled here. The schema comes from the build script and the catalogue comes from
  `src/chavruta/corpus/data/catalog.json`. The `book`/`category_path` columns of the production file still need one
  `SELECT work_id, category_path, COUNT(*) ... GROUP BY 1,2` on the host to confirm the tier/category cross-tab.
- **The book-level key that does exist.** `catalog.json` has 5,423 books, each with `title_en` and a Sefaria
  `path`. Every one of those titles is a key of `corpus/data/licenses.json` (5,828 titles, 5,423/5,423 matched),
  and `corpus/refs.py::work_title_for_ref(ref)` already resolves any stored ref to such a title. So the stable
  book identifier across the catalogue, the reader db and Qdrant is the **Sefaria title**, recovered from the
  ref string at read time, in line with the "derive from the ref, never backfill" rule.
- **What the Qdrant payload carries.** `Chunk.to_payload()` has `work_id` but no `book` or `category_path`. The
  commercial collection's payload was not inspected (no server in this task). If it also lacks a title field, a
  server-side `must_not` on a book is not possible, and a keyword index on `ref` cannot express a title prefix.

### Consequence for R10

1. The `$not`/`deny_work_ids` plumbing (W1-C) is correct and complete for **tier-level** denial (for example deny
   `shut`, `kabbalah`, `midrash`). That already covers the likely school choices.
2. **Book- or category-level denial** (for example "no Tosefta/Niddah", "no Mishneh Torah") cannot ride on
   `work_id`. It needs a second denylist keyed by title, enforced as a **post-filter** (and over-fetch) using
   `work_title_for_ref(hit.ref)`; `retrieval/denylist.py::drop_denied(items, deny, work_of=...)` already accepts a
   resolver for this. The cost is recall under heavy denial, so the retriever should over-fetch when the title
   list is non-empty. A server-side title filter would need a payload field that does not exist and a backfill
   (about 5 points/sec on the on-disk collection, so days), which R10 already rejects.

### Proposed resolver

`resolve_denylist(selected: list[str]) -> Denylist(work_ids: frozenset[str], titles: frozenset[str])`, in a new
module under `src/chavruta/corpus/` (not in `app/`), built once at start-up from `catalog.json`:

1. Entries are catalogue paths (`"Halakhah/Mishneh Torah"`) or tier slugs (`"shut"`).
2. A tier slug goes straight to `work_ids`.
3. A category path becomes `titles = {b["title_en"] for b in catalog["books"] if b["path"] == p or b["path"].startswith(p + "/")}`.
4. A category that is exactly one tier (a fixed table `{"Responsa": "shut", "Kabbalah": "kabbalah", "Chasidut": "chasidut",
   "Musar": "musar", "Liturgy": "liturgy", "Midrash": "midrash", "Tosefta": "tosefta", "Reference": "reference",
   "Second Temple": "second_temple", "Jewish Thought": "jewish_thought", "Mishnah": "mishnah", "Tanakh": "tanakh"}`)
   is promoted to `work_ids`, which keeps it server-side. `Halakhah` and `Talmud` are not exact tiers
   (commentary on the Talmud files under `gemara` too), so they stay as `titles` unless the host cross-tab shows
   they are exact.
5. Per request, take the union of the school and parent entries, then pass `work_ids` to `Query.deny_work_ids` and
   `titles` to a title post-filter next to `drop_denied`.
6. Test it against the catalogue itself: every title resolves to a path, and `work_title_for_ref` of each
   `first_ref`-derived stored ref lands inside the denied set.
