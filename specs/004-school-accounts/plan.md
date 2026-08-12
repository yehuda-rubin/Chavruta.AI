# 004 — School accounts (organisations, shared quota, three roles)

Status: **Option A decided 2026-08-12** (18+ only, three school tiers — see "Decided" below).
The minors track remains blocked on B1/B2. Planned 2026-08-12, then reviewed by four agents
(adversarial, security, feasibility, legal) the same day. The review found two hard blockers and
three errors in the original plan. Everything below is rewritten to reflect that; the earlier
version documented decisions that cannot be implemented as written.

## What this is

A school buys one institution subscription and attaches its people to it. They study on the school's
quota instead of buying their own, and whoever paid can see how it is being used and cap anyone
burning too much of it.

| role | Hebrew | can |
|---|---|---|
| admin | מנהל | everything a teacher can, plus manage teachers, set caps, transfer ownership, billing |
| teacher | מורה | open the panel, invite and remove students, see usage |
| student | תלמיד | study on the shared pool; sees only their own usage |

---

# BLOCKERS — read before doing anything

## B1. Minors are not permitted users of this service, in the contract and in the code

`docs/legal/terms-he.md` §5 and `terms-en.md` §5:

> **The Service is intended for users aged 18 and over, and is not intended for minors.** An account
> found to have been opened by a minor **will be closed**.

And on institutional accounts specifically: *"the pupil is **not** a user of the Service"*, with
`privacy-he.md` §7 adding *"we neither ask for nor need pupil data of any kind, and there are no
pupil accounts."*

It is enforced server-side. `app/security.py::_has_consented` gates every authenticated request:

```python
return bool(meta.get("age_confirmed_18")) and bool(str(meta.get("terms_version") or "").strip())
```

So a 15-year-old accepting an invitation must first tick a box declaring she is 18 — the exact
declaration Terms §5 makes grounds for closing her account. The service would then hold two
contradictory records of one child's age, and the legally load-bearing one (her own declaration,
which the Terms lean on entirely) is the false one, produced by a flow we built.

**Everything in the original "Minors" section was a careful answer to a question the contract says
may not be asked yet.** Admitting minors is its own project: Terms §5 rewrite, Privacy §7 rewrite
(it currently promises the opposite), a guardian-consent mechanism, a signup path that does not
assert 18+, changes to `_has_consented`, and a re-notice to existing users.

## B2. "Nothing belonging to a minor is used for training" is false as designed

This was the original plan's flagship protection, and it was wired to `db.reviewable_questions` —
which is only the OPERATOR's path. `docs/legal/privacy-he.md` §3:

> **ייתכן ש-Nebius ישתמש בנתונים שנשלחו אליו — שאלותיך והמקורות שצירפת — גם לצורך שיפור ואימון
> מודלי הבינה המלאכותית שלו**
>
> **אין בשירות מסלול "ללא אימון", גם לא בתשלום ולא לחשבון מוסדי.**

Every question a pupil types is sent to Nebius and may train Nebius's models, and the policy states
there is no tier — explicitly including an institutional account — that changes this. The
`reviewable_questions` exclusion does not touch it.

Worse, the same section names the only mitigation: *"מה שלא הוזן, לא נשלח — הוא **ההגנה היחידה**
הקיימת כאן."* That rule was written for an adult who read the policy. It cannot be the only
protection for a child typing their own questions unsupervised.

**Three exits, all requiring a founder decision before anything ships:**

1. Narrow the promise in writing and tell schools their pupils' questions go to a provider that may
   train on them. Honest, possibly unsellable to a school.
2. Obtain a no-training or zero-retention arrangement from the provider and rewrite Privacy §3.
3. Do not let a minor's turns reach the default provider at all.

## The fork

**Option A — v1 is 18+ only: teachers and admins, no student role.** Exactly what the contract
already sells. Removes both blockers and most of the review's findings. Roughly a week of work.

**Option B — minors in v1.** Requires B1's whole legal and signup project AND an answer to B2 first.

**Recommendation: A now, B as a separate track if and when.** Not because B is wrong, but because A
is a complete sellable product and B is a legal-commercial decision deserving its own time and the
lawyer's signature. And B must never be discovered halfway: once 400 pupils have accounts you cannot
un-collect them, and the remedy your own Terms promise is to close those accounts.

---

# Corrections to the original plan

**C1. The seat number was arithmetically empty.** 40 seats was chosen because institution is ×40 the
free tier — but ÷40 lands exactly on free:

| | institution | ÷40 | free |
|---|---|---|---|
| daily tokens | 8,000,000 | **200,000** | **200,000** |
| weekly tokens | 21,000,000 | **525,000** | **525,000** |
| weekly lessons | 80 | **2** | **2** |

A 40-member school would pay ₪199 so each member receives, to the token, what they already have for
free. What ₪199 actually buys is **pooling, caps and visibility** — statistical multiplexing, not
per-person capacity. That is a defensible product and it must be said in one honest sentence rather
than discovered by the first school that asks. It also makes the default per-member cap a deliberate
over-subscription (2–4× the even share), which is exactly why the 80% warning matters.

Worse in combination with the no-personal-plan rule: a teacher on `pro` today has 2,000,000/day.
Joining the school drops them to ~200,000 — a **10× downgrade** — and they are then forbidden from
buying their own plan. The one person with a real reason to want more is strictly worse off inside
the org. Either teachers keep a higher cap, or the rule needs an exception.

**C2. The retention rule is a DIFFERENT rule, not a shorter one.** `app/accounts.py::run_retention`
already deletes chats after `CHAVRUTA_CHAT_RETENTION_DAYS` (default **90**) for everyone — keyed on
**inactivity**, and `privacy-he.md` promises *"שיחה שאתה ממשיך לחזור אליה לא תימחק"*. The proposed
minor rule is three months **from writing**, regardless of activity. For an active student these
produce opposite outcomes. Whoever implements it must NOT reuse the existing inactivity sweeper, and
the published promise has to be amended, not merely tightened.

**C3. "Nothing in the existing schema changes shape" was wrong.** A shared pool with per-member caps
means two counters checked and charged in ONE transaction. `db.bump_usage` is single-row by
construction (PK `(owner_id, day, meter)`) and its atomicity is the point. Two sequential calls are
not equivalent: another request interleaves, and `settle_usage` floors at zero per counter so the
compensation is not reversible. This needs a new `bump_pooled` / `settle_pooled` pair — the real cost
centre of the feature. Everything else is CRUD.

---

# Requirements the review added

## Authorization

- **The gate needs a fourth check: `rank(target.role) <= rank(actor.role)`.** Without it a teacher
  can remove the org's admin — all three originally-stated checks pass. Either the org goes headless
  or the teacher inherits it.
- **`org_members.role` is authoritative for permissions; `orgs.owner_id` for billing only.** Two
  sources of truth for "is admin" is where the second escalation lives. Written in one transaction.
- **Mount the router with the gate as a dependency**, not per-route: `APIRouter(dependencies=[...])`.
  A route nobody remembered to test still cannot skip it.
- **Fail with 404, not 403**, following `_require_admin`'s existing convention — a 403 confirms org
  ids and memberships to an outsider.
- **Unique constraint on `org_members.owner_id` where `accepted_at IS NOT NULL`.** Nothing otherwise
  stops two accepted memberships, and quota resolution has no answer for which pool a turn charges.

## The under-18 flag

- **It must be a column in `chavruta.db`, never read from Supabase JWT metadata.** The two functions
  that must honour it cannot read metadata: `db.reviewable_questions` is pure SQL, and the retention
  sweeper is a background thread with no HTTP caller. Put it in metadata and the protection fails
  **open**, silently.
- **Do not let "default minor" mean "everyone".** Every existing account lacks the flag; a literal
  default-minor rule makes `reviewable_questions` return `[]` for the whole user base and
  `harvest_user_questions.py` goes to zero **with nobody noticing**, because a privacy gate returning
  nothing looks exactly like "no new questions". Derive adult from the `age_confirmed_18` claim that
  already exists; set `is_minor` explicitly on the membership row.
- **The school may only set the flag TO minor.** Clearing it must require the account holder or the
  operator, and every change goes to `org_access_log`. Otherwise one teacher toggling a roster
  un-protects 40 children across three mechanisms at once (review, marketing, retention).
- **The flag persists after the student leaves.** Otherwise leaving silently downgrades them.

## Keeping conversation text out

- **The panel reads exclusively from `usage_events`.** `db.record_usage_event` has a fixed column
  list of measurements — no text ever reaches it. `sessions` and `messages` are off-limits to
  `app/orgs.py`, including exports.
- **`sessions.first_q` holds the raw question.** Building the topic view by joining `sessions` — the
  intuitive place, since that is where per-chat rows live — hands every teacher the verbatim opening
  sentence of every conversation. This is the single most likely way decision 1 gets broken, because
  the column is not called "message".
- **"Topic" is a closed vocabulary**, not a generated label. A label derived from the question echoes
  the sensitive part by construction, and costs money per turn.
- **Moderation flags go to the operator, never to the school.** A "your student was flagged"
  notification is content by another name, and it is the first thing a school will ask for.

## Invitations

- **Invite by CODE, not by owner id.** The admin generates a school-scoped, expiring, N-use join
  code; the student pastes it in Settings beside the existing coupon field. This satisfies "the
  member performs the act" exactly, and it removes three problems at once: the UUID-copying UX, the
  email directory we do not have (`owner_id` is a Supabase UUID; the app DB stores no email), and the
  enumeration oracle below. It reuses `coupons.generate_code`, its throttle, and `redeem_coupon`'s
  one-transaction pattern.
- **The refusal must be uniform to the inviter.** "Refused, showing the date it lapses" turns the
  invite endpoint into an oracle: buy one subscription and you can learn, for any account id, whether
  it exists, whether it holds a paid plan, and when that plan ends. The reason and the date belong to
  the *invitee*.
- **The precondition tests the wrong property.** It must be "no active paid plan AND owns no org AND
  holds no accepted membership" — and a coupon-granted plan is stored as `status='canceled'` with a
  future `current_period_end`, so test `plans.canonical(db.get_plan(x)) != 'free'`, not the
  subscription status.
- **Three enforcement points, not one**: `/billing/checkout`, `coupons.redeem`, and `/admin/grant`.
  Re-check at webhook time too — a checkout in flight while an invite is accepted reaches the
  forbidden state with no rule broken.
- Invite expiry, per-org rate limit, and revocation of pending invites on removal.

## Quota

- **The per-member cap has two documented bypasses right beside it.** `_reserve_tokens` falls through
  to `db.spend_credits` and then to `db.BYOK_TOKENS` sized from the plan tier. A member inheriting
  `institution` silently gets an 8M/day BYOK allowance. State that the cap binds on every admission
  path, or disable credits and BYOK for members.
- **The lesson pool is a separate meter and the plan never mentioned it.** If a member's effective
  plan becomes the org's, each of 40 members gets 80 lessons/week — 3,200 lessons from one ₪199
  subscription, each running the agentic loop over a large source pool.
- **Resolve the pool identity once per request and carry it through settlement.** `_reserve_tokens`
  and `_settle_tokens` resolve the owner independently; a member removed in between settles against
  their personal counter and the school's reservation is never released. The async paths widen that
  window to minutes.
- **Model the pool as a synthetic owner id** (`org:<uuid>`) in `usage_counters` — the PK already
  indexes it and `_counts`/`week_days` work unchanged, so the pool itself needs no schema change.
- **Seat admission must be check-and-increment in one transaction**, following `bump_usage`'s own
  pattern, or concurrent accepts each see room and overrun the cap.

## Lifecycle

- **`db.purge_owner` knows nothing about orgs.** An admin deleting their account leaves
  `orgs.owner_id` dangling and 40 members resolving quota to a dead owner. Refuse deletion while the
  account owns an org — the same shape as decision 3 (block and explain, never touch it silently).
- **`subscriptions.owner_id` is a PRIMARY KEY and the PayPlus token belongs to the person who
  checked out.** "Transfer ownership" cannot move the money: the ex-principal's card keeps being
  charged, invoices keep carrying their name, and only they can cancel. Defer transfer from v1 — it
  is a one-row UPDATE an operator can run — or scope it explicitly to roster control, not billing.
- **`orgs.plan` would be a second copy of `accounts.plan` that the lapse path never writes.**
  `sweep_downgrades` calls `db.set_plan(owner, "free")` and nothing touches `orgs`. Derive the org's
  entitlement from the owner's account, or accept a reconciliation job.
- **`usage_events` has no `org_id`.** Joining by *current* membership means a student who used the
  product privately for a year has that personal usage appear in a teacher's panel retroactively, and
  a student who leaves erases the term's numbers. Stamp membership at write time.
- **`org_access_log` needs a retention rule.** An indefinite log of which teacher looked at which
  child sits badly three paragraphs below a decision to purge that child's data at three months.
- **`feedback` and `message_reports` are not covered by `purge_owner`** — free text and safety flags
  about a child, retained forever, with the messages they point at cascaded away.

## Deployment

- **Rate limiting is per-IP** (`app/security.py`, 20/min). A class of 30 behind one school NAT shares
  one bucket: three active students exhaust it and the rest get 429s. This is the first deployment
  shape where many paying users share an egress IP. Key admission on owner id for authenticated
  traffic; keep the IP window for anonymous.
- **Decide which frontend.** `web/` (Next.js) and the static `app/frontend/public/ui/chavruta.html`
  both exist. Clone `web/app/admin/page.tsx` — a working, `me()`-gated, RTL dashboard — rather than
  fitting tables into `SettingsModal`.

## Reuse rather than build

- `db.usage_by_owner` / `usage_by_intent` / `usage_by_hour` are the panel's three charts already;
  they need one `owner_ids` filter.
- The 80% warning needs no machinery: `db._counts` already returns day and week totals.
- The invite/accept flow is `app/coupons.py` with the nouns changed.
- `_require_admin`'s 404-not-403 shape is the right model for `require_member(org_id, min_role)`.
- **Cut the role simulator from v1.** It means seeding a synthetic school with synthetic members and
  usage and threading a simulated role through the gate, `/me` and the panel — the whole surface, for
  a fixture only the operator sees. Creating a real test school with two throwaway accounts takes
  five minutes. Highest cost-to-value item in the original plan.

---

# Legal work required

Two releases, because the first two items must not be held behind an unbuilt feature.

**Release A — now, independent of school accounts. Privacy 1.8 → 1.9:**

- Appoint the privacy officer: **Yehuda Rubin, ממונה על הגנת הפרטיות, from 2026-08-12**, with a
  contact address. §11 currently states that no appointment has been made and that the obligation
  does not apply.
- **Fix a statement that is already false**: §11 says the service *"רושם מדדים ולא תוכן"*. Version
  1.8 (10.8.2026) granted the operator the right to review conversation content. This is a
  pre-existing inaccuracy, unrelated to schools.
- Fix the §12/§13 cross-reference in `privacy-he.md` (the Hebrew says 12, the English says 13; 13 is
  correct) — the officer's contact goes in that exact clause.

**Release B — with the feature. Privacy 1.9 → 1.10, Terms 1.10 → 1.11.** Six published sentences
must be **reversed**, not extended: "there are no pupil accounts", "the pupil is not a user", "we
neither ask for nor need pupil data of any kind", "we do not knowingly collect personal information
from minors", "an account found to be a minor's will be closed", "lessons you create are not deleted
automatically". The changelog must name them as reversals — the 1.4→1.10 lineage said the opposite
four times, and a regulator reads the whole file.

Also required in B: the organisation as a named recipient in §4 (the current list is sub-processors
plus legal compulsion; a school is neither); a ninth purpose in §11, whose *"למטרות אלה בלבד"*
framing is self-executing and requires advance notice; §1 itemisation of membership, role, caps, the
flag and the access log; and a new section stating what the institution sees and what it never sees.

**Every change lands in five places**: the four `docs/legal/*.md` files and `web/lib/legal.ts`. There
is no test enforcing parity — worth adding. Note also that bumping `TERMS_VERSION` does **not**
currently force re-acceptance (`web/app/page.tsx` checks only that a version is present), which is a
deliberate decision to make given that release B changes who may see a user's data.

**A missing document, not a clause:** there is no institution contract and no processing/outsourcing
agreement in `docs/legal/`. If a school determines the purposes for its pupils' processing it may be
a בעל מאגר with us as a מחזיק, which triggers a written agreement under the Data Security
Regulations. Likely a hard prerequisite to signing the first school.

## For the lawyer

Not legal advice; flags only. Whether the service now falls within amendment 13's triggers with pupil
accounts and per-member reporting (the published text asserts three negatives, at least one already
stale) · whether a record of a person's Torah study questions is מידע רגיש, and more so for a child ·
whether adding minors moves the database's security level · parental consent and a minor's capacity,
and whether a school can consent on a pupil's behalf · school as בעל מאגר vs מחזיק and the agreement
above · Ministry of Education circulars on pupil privacy and ed-tech suppliers · whether a minor's
continued use binds them to amended terms · whether an institutional purchase is a consumer
transaction at all (Terms §10's 14-day right and the cancellation-fee cap are consumer provisions,
and `plans.refund_quote` deliberately does not deduct consumed value — calibrated for one person and
inherited unchanged at 40×) · cross-border transfer resting on consent where the data subject is a
child · whether the no-marketing-to-minors rule should refuse the `marketing_consent` write rather
than override it at send time.

---

# Decided 2026-08-12: Option A, with three school tiers

The founder took Option A (18+ only — teachers and adult students, no minor role) and set three
school sizes: **up to 20 · up to 50 · up to 100 members.**

## The pool must grow with the seats, or bigger schools get less per person

This is C1 again, sharper. Three tiers sharing today's single institution pool (8M/day) would give:

| seats | per member/day | vs free (200,000) |
|---|---|---|
| 20 | 400,000 | **2×** |
| 50 | 160,000 | **0.8×** |
| 100 | 80,000 | **0.4×** |

A larger school would pay more and receive less per person than its members already get for free.
So the pool scales with the seat count. Targeting **2× the free allowance per member**:

| tier | seats | daily pool | weekly pool | lessons/week |
|---|---|---|---|---|
| A | 20 | 8,000,000 | 21,000,000 | 80 |
| B | 50 | 20,000,000 | 52,500,000 | 200 |
| C | 100 | 40,000,000 | 105,000,000 | 400 |

Conveniently, **tier A is exactly the institution tier that already ships** (8M / 21M / 80) — it
needs a seat cap and a name, nothing else. The lesson meter scales on the same rule; leaving it at 80
for all three would repeat the identical mistake in the pool that actually costs the most per unit.

## What the school is shown is the PER-MEMBER figure

`public_catalogue` states a ratio and never an absolute, and the `multiple` field is what carries it.
For a pooled tier that field stops being meaningful: tier C is ×200 the free tier in total and ×2 per
person. **×200 is true and useless.** The honest sentence, and the one that actually sells, is *"each
member gets about twice the free allowance, and unused capacity goes to whoever needs it"* — pooling
is the product, so say so rather than printing a number that flatters and misleads.

This means `TIERS` and `public_catalogue` need a per-seat notion the current model has no room for.
The invariant they enforce today ("every paid tier is a clean multiple of free across every
dimension") still holds per member; the code has to express which figure it is stating.

## Before setting prices: these caps are the cost ceiling

A 100-seat school that maxes its pool consumes 40M normalized tokens a day. Whether that is
profitable at any given price is not something to reason about — **it is already being measured.**
`usage_events` records real `prompt_tokens` and `completion_tokens` for every production turn, so
cost per turn is a query, not an estimate. Multiply out before pricing tier C. A tier that loses
money precisely when it succeeds is the worst shape a plan can have, and it is invisible until a
school actually uses what it bought.

Related, and still unresolved from the review: `plans.refund_quote` deliberately declines to deduct
consumed value, reasoning that on one monthly instalment the pro-rata share is a few shekels not
worth arguing over. At 100 seats a school can study for 13 days against a 40M/day pool and exercise
the 14-day cancellation for a near-full refund. Cheap to fix now, expensive after the first school
does it, because by then it is a precedent.

# Scope

**v1 (18+ only)** — org creation on institution checkout · join codes · roles · shared pool
with per-member caps · usage view from `usage_events` · 80% warning · leave/remove. No student role,
no minors work, no B2 question.

The default per-member cap is a deliberate over-subscription — around 3–4× the free allowance against
an even share of 2× — so a heavy user can exceed their share while the pool still holds. That is
what makes pooling worth buying, and it is why the 80% warning is not decoration.

**Explicitly out either way** — conversation text · user impersonation · per-student pricing ·
cross-org anything · ownership transfer in v1 · the role simulator.

**Ordering** — the pooled counter (`bump_pooled`/`settle_pooled`) first, since everything else
depends on where the counter lives and it is the only part where correctness costs money. Then the
resolver in `app/orgs.py` (NOT in `plans.py`, which is pure and DB-free by design), rewiring
`_reserve_tokens`, `_charge_lesson_unit`, `_record_event` and `/me`. Green `test_quota.py` and
`test_byok_quota.py` is the definition of "existing single users unchanged". Then the gate and
endpoints with the cross-org tests written alongside, then billing/coupon refusals, then UI.
