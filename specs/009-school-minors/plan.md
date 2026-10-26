# Implementation Plan: School-Track Minors Support

**Branch**: `001-chavruta-redesign` (no separate branch yet) | **Date**: 2026-10-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/009-school-minors/spec.md`

## Summary

Open Chavruta.AI to students aged 12–17, starting with the school track:
- **Signup**: students sign up themselves with a birth month and year, stored server-side and write-once.
- **School link**: by account ID with the student's approval, or by a capped join link.
- **Parent link**: optional, child-approved. A linked parent may correct the child's age and switch content off.
- **Protections that cannot be disabled**:
  - A Hebrew crisis screen before generation, which shows a fixed reply with ער"ן / סה"ר / 100 and alerts a
    human. It never reports to authorities automatically.
  - A minor safety block in every mode's prompt, with no psak.
  - Minors' traffic is routed only to Claude API.
- **Data protection**: every message written as a minor carries an immutable deletion date (`minor_until`) that
  excludes it from review and training forever and deletes it after 60 days.
- **Content**: everything is on by default. The school admin and the linked parent can switch off books or
  categories. The union of their choices applies on every retrieval path, with a final citation post-filter.

## Technical Context

**Language/Version**: Python 3.13 (backend, `.venv`), TypeScript / Next.js App Router (`web/`)

**Primary Dependencies**: FastAPI, sqlite3, Qdrant client, Supabase auth (JWT), OpenAI-compatible `CloudLLM`
plus a new `anthropic` preset (R8), and `app/email_pool.py` for alerts.

**Storage**: `chavruta.db` (SQLite), with a migration to schema 35 (see [data-model.md](data-model.md)). The
Qdrant collection `chavruta_commercial` is **unchanged**: no payload backfill is needed.

**Testing**: pytest (`tests/unit`), the existing proxy-coverage test, retrieval-only probes, and synthetic
Hebrew/English test sets for crisis, benign-sensitive and minor-rules cases. LLM-calling evals need the
founder's approval.

**Target Platform**: the production Nebius Cloud VM (docker + nginx), and locally `scripts/serve.ps1`.

**Project Type**: web application (FastAPI backend + Next.js frontend)

**Performance Goals**:
- Crisis screen adds no more than 1.5 s to a minor's turn at p95. It runs concurrently with retrieval and gates
  only the generation start.
- Alerts are delivered in under 5 minutes (SC-002).

**Constraints**:
- Fail-closed on minor backend availability: never fall back to Nebius for minors.
- Fail-safe on classifier errors: answer normally and log, never block.
- No message text in alerts, panels or admin views of minors.
- No real user text in tests or the repo.

**Scale/Scope**: early stage, from a few schools to fewer than 5,000 minors in year one. Crossing 10,000 data
subjects triggers the legal re-check in `docs/MINORS_READINESS.md` §5 P0-10.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | How |
|---|---|---|
| I. Grounded, never invented | ✅ | Minor rules add constraints only. A fully denied query returns the honest no-permitted-source state (FR-018). The citation post-filter can only remove sources, never add them. |
| II. Deployment-agnostic | ✅ | All gates are config- or DB-driven. Offline/local mode (`local` owner) has no age record and behaves as an adult, as today. The `anthropic` preset is a preset like the others. |
| III. Extensible corpus | ✅ | The denylist works by `work_id` and category, resolved at read time. New works need no change, and there is no payload backfill. |
| IV. Bilingual | ✅ | The crisis reply, disclosures, safety block and phrase layer exist in Hebrew and English. Hebrew is primary. |
| V. Measurable trustworthiness | ✅ gate | Adult eval must show no regression (SC-008). New synthetic sets measure SC-002 to SC-005. |
| VI. Simplicity | ✅ | Reuses `org_invites`, `email_pool`, `run_retention`, `reviewable_questions` and the `audience` plumbing. Adds no new vendor and no new service. |
| VII. UX | ✅ | One-tap help contacts, a child-friendly disclosure, and honest blocked states (`adult_terms_required`, `minor_no_purchase`). |
| VIII. Halachic humility | ✅, strengthened | For minors: no ruling for practice, and a referral to a rav or teacher in every mode. |
| Privacy constraint | ✅ | Minimal age data (month and year only), alerts with no text, and short retention. |

No violations, so Complexity Tracking is empty.

**Post-design re-check**: the design artifacts introduce no new principle conflicts. ✅

## Project Structure

### Documentation (this feature)

```text
specs/009-school-minors/
├── spec.md
├── plan.md              # this file
├── research.md          # R1–R12 decisions
├── data-model.md        # schema 35
├── quickstart.md        # validation guide
├── contracts/api.md     # endpoints + error codes
├── checklists/requirements.md
└── tasks.md             # next: /speckit-tasks
```

### Source Code (touched or new)

```text
app/
├── db.py              # migration 35; save_message sets minor_until; reviewable_questions filter;
│                      # list_flagged_messages/list_feedback redaction; purge_owner (+ referral_* fix)
├── minors.py          # NEW: age records, is_minor/adult_from, parent links, join requests, effective denylist
├── crisis.py          # NEW: phrase layer + classifier call + fixed reply + alert dispatch
├── security.py        # require_auth: age_required / adult_terms_required / minor_no_purchase
├── orgs.py            # accept_invite sets is_minor; safety_contacts; content settings; join-request approval
├── accounts.py        # run_retention second pass (minor_until)
├── marketing.py       # exclude minors from recipients
├── moderation.py      # untouched by this feature (defamation false-positive fix tracked separately)
└── api.py             # new routes (contracts/api.md); minor → anthropic preset; crisis gate before generation;
                       # audience_minor flag into prompts; commerce refusals
src/chavruta/
├── llm/presets.py     # NEW anthropic preset
├── llm/base.py        # sources wrapped as untrusted data
├── generation/grounded.py   # MINOR_SAFETY_HE/EN block appended in every mode
├── retrieval/hybrid.py      # denylist threaded through every path
└── store/qdrant_store.py    # _build_filter: $not → must_not
scripts/send_broadcast.py    # consent + minor filter
config/crisis_contacts.json  # NEW, versioned, verified before release
web/
├── components/SignIn.tsx    # birth month/year replaces 18+ checkbox for new signups
├── components/ConfirmConsent.tsx  # age_required + adult_terms_required flows
├── app/school/page.tsx      # join-request by account ID, content settings, safety contacts, alerts.
│                            # The existing student-code button is NOT modified.
├── app/parent/              # NEW: link child, correct age, content switches
├── components/CrisisCard.tsx  # NEW: fixed reply + one-tap contacts
├── lib/api.ts + next.config.mjs  # new prefixes; docker/nginx.conf too
└── (pricing/plans/referral UI hidden when me.is_minor)
docs/legal/terms-*.md, privacy-*.md  # FR-032 revision, needs a lawyer's sign-off
tests/unit/                  # test_minors.py, test_crisis.py, test_denylist.py, test_minor_retention.py …
tests/eval/minors/           # synthetic sets only
```

**Structure Decision**: use the existing web-application layout (`app/` backend, `src/chavruta/` core,
`web/` frontend). Two new backend modules, `app/minors.py` and `app/crisis.py`, keep the minor logic out of
the already very large `api.py`.

## Delivery order (for /speckit-tasks)

1. **Foundation**:
   - schema 35 and `app/minors.py`;
   - the `require_auth` codes;
   - `minor_until` on save;
   - the review, retention, marketing and commerce gates;
   - the purge fix.
   This is free to test and gives the most protection for the effort.
2. **Signup UX**: birth month/year, the disclosure, `/me` fields, and hiding commerce UI.
3. **Minor LLM routing**: the `anthropic` preset, fail-closed. Verify the API with the `claude-api` skill.
4. **Answer rules**: the safety block and untrusted-source wrapping. Gated by an eval run that needs approval.
5. **Crisis path**: phrase layer, classifier, fixed reply, alerts, and safety contacts. Measured on synthetic
   sets before release.
6. **School linking**: join requests and minor-aware `accept_invite`.
7. **Content denylist**: across all retrieval paths, plus the post-filter. Measured with retrieval-only probes.
8. **Parent link**: age correction and content switches.
9. **Turning 18** flow.
10. **Legal text** (FR-032/033) and the pre-launch gates in quickstart §6.

**Deploy gate**: no route opens to minors until steps 1–5 and 10 are done. The age signup (step 2) can ship
first because it only adds data. Per the deploy-gate rule, show that each deploy cannot affect users, or that
15 minutes of traffic were quiet.

## Complexity Tracking

No constitution violations to justify.
