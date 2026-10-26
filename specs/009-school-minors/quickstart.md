# Quickstart: validating School-Track Minors Support

These steps run locally against the dev profile. Use `.venv\Scripts\python.exe` (Python 3.13), not the default
`python`.

**Before you start:**
- Any step that calls the LLM costs budget. Get the founder's approval before running it (model-runs rule).
- Every test set is synthetic. No real user text is used.

## 0. Prerequisites

- `scripts/serve.ps1` stack up (Qdrant + API + web), Supabase test project.
- The `anthropic` preset configured, because minors' traffic requires it (research R8).
- Two test accounts: an adult acting as school admin and parent, and a minor (birth year about 14 years ago).

## 1. Unit and contract tests (free, no LLM)

```powershell
.venv\Scripts\python.exe -m pytest tests/unit -q -k "minor or age or crisis or denylist or parent or join_request or proxy_coverage"
```

What they must show:
- The age record is write-once by the owner. A parent or the operator can change it, and every change is logged.
- Signups under 12 are refused (FR-001, FR-004).
- A legacy account with `age_confirmed_18` and no age record is treated as an adult (FR-007b).
- `minor_until` is set at write time and never changes. Review excludes it, retention deletes on schedule, and
  both still hold after `adult_from` (FR-024–FR-026, FR-031).
- The marketing recipient list and `send_broadcast.py` exclude minors (FR-027).
- Billing, coupon and referral routes return `403 minor_no_purchase` (FR-008/009).
- The admin flagged-message and feedback views omit `owner_id` and full text for minor rows (FR-028).
- `purge_owner` clears every new table, plus the `referral_*` tables.
- The proxy-coverage test passes with the new prefixes (`/parent`, plus the new `/orgs/*` and `/account/*`
  routes).

## 2. Retrieval denylist (free, retrieval only, no LLM)

Disable one tractate and one category for a test org. Then run the retrieval-only probe for a minor query set
that targets them in every mode. Expect:
- 0 denied `work_id`s in candidates or final citations, on every path: fallback, floors, `fetch_by_refs`,
  link expansion and agentic fetch (SC-005).
- An adult in the same org is unaffected (FR-023).

## 3. Crisis screening

**Phrase layer only (free):** run it on the synthetic distress set and the synthetic benign set (study questions
on sensitive sugyot). Record recall and false-positive rate.

**With the classifier (costs budget, needs approval):** run the full screen on both sets.
- **Targets**: at least 95% fire on distress (SC-002), and no more than 2% fire on benign (SC-003).
- **Check**: a fired case returns the `crisis` payload. No generation call is made, a `crisis_alerts` row exists
  with no text, and an email reaches the safety contact within 5 minutes.
- **Check**: if the classifier errors, the student gets the normal answer and the turn is logged as
  `screen_unavailable`.

## 4. Minor answer rules (costs budget, needs approval)

Run the synthetic minor set across all modes. Expect:
- 0 rulings for practice.
- Every psak-type question names a rav or teacher.
- Every companion or romantic persona request is declined.
- Off-topic requests are redirected (SC-004).

Then run the existing eval set for adults. It must show no regression (SC-008, Principle V gate).

## 5. End-to-end UI walk

1. **Signup**: sign up as a minor and enter a birth month/year. The adult checkbox is absent and the
   child-friendly disclosure appears. The student can study unlinked, and pricing, plans and the referral
   programme are hidden.
2. **School linking**: the school admin sends a join request by account ID, and the student approves it.
   Alternatively, the student opens a capped join link, and user N+1 is refused. The school panel never shows
   the student's age.
3. **Parent linking**: the parent links, and the child approves. The parent corrects the child's age and
   switches a book off. The book is now absent from the child's answers.
4. **Turning 18**: set `adult_from` in the past for the test minor. Sending is blocked until the adult terms
   are accepted. Marketing consent is offered as optional. Old messages are still excluded from review.

## 6. Pre-launch gates (outside the software)

- The lawyer has reviewed the Terms and Privacy revisions (FR-032) and the open questions in
  `docs/MINORS_READINESS.md` §7.
- A written incident procedure exists: who reads alerts, the response time, and when to call 105 or the police.
- The crisis contact numbers have been verified on the official sites.
- The crisis reply text has been approved by a human, ideally a mental-health professional.
