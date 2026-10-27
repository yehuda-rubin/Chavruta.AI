# Tasks: School-Track Minors Support

Source: [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/api.md](contracts/api.md).

Rules for every task:
- Use `.venv\Scripts\python.exe`.
- Make no LLM or API calls in tests (synthetic data, injected fakes).
- Never put real user text in code or tests.
- Do not commit.
- Do not revert other people's uncommitted changes.
- Do not touch the existing student-code button.

## Wave 1: parallel (disjoint files)

### W1-A Backend foundation, story 1 and story 5 data gates (`app/` only)

**Schema and age records**
- [x] T001 Migration 35 in `app/db.py`, adding:
  - new tables: `age_records`, `age_record_log`, `org_join_requests`, `parent_links`, `content_denylist`, `crisis_alerts`;
  - new columns: `minor_until` on `messages`, `saved_lessons`, `saved_source_sheets`; `org_members.is_minor`; `orgs.safety_contacts`;
  - index `idx_messages_minor_until`.
- [x] T002 `app/minors.py` with these functions: `get_age`, `set_age_once` (≥12, write-once), `correct_age(actor_kind)` (parent/operator, logged), `is_minor(owner, today)`, `adult_from` (first day of the month after the 18th-birthday month), `adult_terms_required`, `accept_adult_terms`, `minor_retention_days()` (`CHAVRUTA_MINOR_RETENTION_DAYS`, default 60).

**Data gates**
- [x] T003 `save_message`, `save_lesson` and `save_source_sheet` set `minor_until` at write time from the author's age record. Never update it afterwards.
- [x] T004 `reviewable_questions` excludes messages where `minor_until IS NOT NULL`.
- [x] T005 `accounts.run_retention` adds a second pass that deletes rows where `minor_until <= now`, regardless of activity.
- [x] T006 `purge_owner` covers every new table and the `referral_*` tables (fixes an existing gap).
- [x] T007 `marketing.list_marketing_recipients` excludes minors. `scripts/send_broadcast.py` uses the consent + minor filter.
- [x] T008 `list_flagged_messages` and `list_feedback` return `{id, category, snippet_redacted, created_at, minor: true}` for minor rows, with no `owner_id`, `session_id` or full text.

**Auth gate and endpoints**
- [x] T009 `security.require_auth`:
  - Return `403 age_required` for an account with no age record and no legacy `age_confirmed_18`.
  - Count a legacy `age_confirmed_18` as adult.
  - Keep `/me` and `/account/*` exempt.
- [x] T010 Endpoints `POST /account/age` and `POST /account/adult-terms`. `/me` gains `is_minor`, `age_required`, `adult_terms_required` and `school_linked`.
- [x] T011 `403 adult_terms_required` on message-sending routes. `403 minor_no_purchase` on billing, coupon and referral routes.
- [x] T012 Unit tests for all of the above, in `tests/unit/test_minors_foundation.py`.

### W1-B Crisis screening module, story 2 (new files only)

- [x] T020 `app/crisis.py`: `screen(text, lang) -> CrisisResult|None`.
  - Deterministic Hebrew/English phrase layer: niqqud strip, final-letter normalisation, prefix/suffix tolerance, transliterations.
  - Classifier hook `classify(text, llm_call)` with an injected callable that returns JSON. On error it fails safe and returns `screen_unavailable`.
  - Fixed human-written reply texts in Hebrew and English.
- [x] T021 `crisis_contacts.json` lists ער"ן, סה"ר, police 100 and 105, each marked `verified: false` until the founder verifies it.
- [x] T022 Synthetic test sets under `tests/eval/minors/`: distress cases, and benign cases built from study questions on sensitive sugyot. Unit tests measure the phrase layer's recall and false-positive rate.

### W1-C Content denylist in retrieval, story 4 (`src/chavruta/retrieval`, `src/chavruta/store`)

- [x] T030 `QdrantStore._build_filter` supports a `$not` key (must_not MatchAny).
- [x] T031 Thread a `deny_work_ids` field on `Query` through every path: `_filters`, `_work_filter`, unscoped fallback, base and foundational floors, `fetch_by_refs`, link expansion, agentic fetch.
- [x] T032 Add a `drop_denied(citations, deny)` post-filter helper.
- [x] T033 Add unit tests with a fake store. Each path must be proven to honour the denylist, and an empty denylist must leave behaviour byte-identical.
- [x] T034 Write a free investigation note on whether `data/search_index.db` book ids map to corpus `work_id`, and propose a category→work_id resolver.

### W1-D Minor answer rules, story 3 (`src/chavruta/generation`, `src/chavruta/llm`)

- [x] T040 Add `MINOR_SAFETY_HE`/`MINOR_SAFETY_EN` in `grounded.py` and an `audience_minor` flag that appends the block in every mode. With `audience_minor`, drop the "apply to modern cases" instruction.
- [x] T041 Add a test proving adult prompts are byte-identical to before.

## Wave 2: after Wave 1, sequential (all touch `app/api.py`)

- [x] T050 Route minors only to an LLM preset that is approved for minors. Configure the approved preset with `CHAVRUTA_MINOR_LLM_PRESET`. If no preset is set or the provider is unavailable, fail closed with `503 minor_backend_unavailable`. Nebius is blocked for minors until it confirms in writing, because Services Agreement §4.1.6 lists "personal data of minors" as Sensitive Personal Data. The founder emailed privacy@nebius.com on 2026-10-26 and is awaiting a reply. Enable ZDR either way. Claude is a later option.
- [x] T051 Wire the crisis gate before generation for minors, add the `crisis` payload, and add alert dispatch through `email_pool` plus the `crisis_alerts` row.
- [x] T052 Wire `audience_minor` into all modes. Do not offer the shut/responsa walkthrough to minors: its prompt says "rule clearly le-ma'aseh", and the minor block only overrides that text, which is still present.
- [x] T053 Wire the effective denylist (org ∪ parents) into `Query`, and apply the post-filter. Per the R10 investigation, `work_id` is a tier slug (15 values), not a book. Use two mechanisms:
  - **Whole tier**: deny it in Qdrant with `deny_work_ids` (`must_not`).
  - **Book or category**: resolve to Sefaria titles from `catalog.json` and drop them with a post-filter, using `drop_denied(work_of=corpus/refs.py::work_title_for_ref)`. Over-fetch to keep recall.

  Also cover `src/chavruta/pipeline/pipeline.py`:
  - **Agentic NEED_SOURCES fetch (~263)**: its fresh `Query` loses the denylist.
  - **`base_sources_for_refs` (~826)**: lesson base texts need the denylist.
  - **`_fetch_tanakh_refs` guard (~617)**: verification only, but still a bypass.

  Finally, apply `drop_denied` to citations and source sheets in `app/api.py`.
- [x] T054 Add the school-linking endpoints (join requests) and the minor-aware `accept_invite`.
- [x] T055 Add the parent endpoints, the content settings endpoints, safety contacts and the alerts endpoints. Add the proxy prefixes to `nginx.conf` and `next.config.mjs`.

## Wave 3: frontend (`web/`)

- [x] T060 Signup with birth month/year, the child-friendly disclosure, and the `age_required` and `adult_terms_required` flows.
- [x] T061 Hide pricing, coupons and referral when `me.is_minor`. Add a `CrisisCard`.
- [x] T062 School page: join request by account ID, content settings, safety contacts, alerts. Do not modify the student-code button.
- [x] T063 Parent page, served at `/family`, not `/parent`, because `/parent` is proxied to the API in `nginx.conf` and `next.config.mjs`.

## Wave 4: release gates

- [ ] T070 Eval runs that cost budget, each needing approval: the crisis classifier, minor rules, and the adult no-regression check.
- [ ] T071 Revise the legal text (FR-032/033) and get a lawyer's review.
- [ ] T072 Write the incident procedure, verify the contacts, and approve the crisis reply text.

## Follow-ups found in Wave 1

- [x] T080 Make `scripts/moderation_report.py` handle the redacted minor rows from `list_flagged_messages`. Today it raises KeyError, because those rows have no `owner_id`, `source`, `role`, `session_id` or `message_id`.
- [x] T081 Delete `feedback` rows written by minors on the minor schedule. Today they are redacted but have no `minor_until`.
- [x] T082 `minors.correct_age` checks only the actor kind. Its callers in Wave 2 must verify an active `parent_links` row or the operator gate.
- [ ] T083 The crisis phrase-layer metrics (recall 68/71, false positives 0/66) come from sets written by the same agent that wrote the phrase layer. Build an independent set before relying on them.

## Parental consent for minors without a school (founder decision 2026-10-26, option 2)

A minor who is not linked to a school can study only after a parent has consented. Either of these counts as consent:
- an active `parent_links` row, where the parent has an account; or
- a parent who approved through an emailed consent link, without needing an account.

Until a parent consents, message-sending routes return `403 parental_consent_required`. A school link also satisfies consent, because the school holds parental consent.

- [x] T090 Backend: add a `parental_consents` table with these columns:
  - child id;
  - parent email (kept only as proof of consent);
  - token hash;
  - status (`pending`, `approved`, `declined`, `expired` or `revoked`);
  - `sent_at`, `decided_at`, plus the IP and user agent at decision time, as proof.

  Endpoints:
  - `POST /account/parental-consent {parent_email}`: the minor requests consent. Rate-limited, with resend and a 7-day expiry. The parent address must not be the child's own.
  - `GET /consent/{token}`: public. Shows what the parent is agreeing to: the minor rules, what is collected, the 60-day retention, no training, and alerts.
  - `POST /consent/{token} {decision}`: records the parent's decision.
  - `DELETE /account/parental-consent`: the parent revokes through a link in the email. The child cannot revoke.

  Gate this into `require_auth` / `minors.gate_error`. Send the parent email through `app/email_pool.py`. It is a transactional product email: in Hebrew, with no marketing. Add the `/consent` prefix to `nginx.conf`, `next.config.mjs` and `api.ts`, and purge the rows with the child.
- [x] T091 Frontend: on the age step, a 12–17 user without a school link enters a parent's email. Show a "waiting for parental consent" state with a resend button. Add a public `/consent/[token]` page.
- [x] T092 Update the legal drafts: terms 5.1(c) and privacy §7 now allow an unlinked minor once a parent consents by email. Add a parent-consent text and a consent-email template.
- [x] T093 Under-12 refusal: when `POST /account/age` refuses with `under_minimum_age`, delete the account immediately (`purge_owner` plus the Supabase user). Do not leave an account that can only sign out. The frontend shows that the account was deleted. Founder decision 2026-10-26.
- [ ] T094 Add a frontend revoke page at `/parent-consent/revoke/[token]` that calls `POST /consent/revoke/{revoke_token}`. The endpoint is public and takes no body. It returns `{status:"revoked"}`, 404 when the token is unknown, and 409 `already_decided`.

**State at pause, 2026-10-26:**
- Committed and pushed up to `2d0781e`.
- Not yet committed: T050, T090, T091, T093, the frontend (T060–T063), and the legal drafts.
- Next steps: T094, then a full test run, then a commit.
- Minors stay blocked until a preset is added to `APPROVED_MINOR_PRESETS`. The list is empty while we wait for Nebius to reply.
