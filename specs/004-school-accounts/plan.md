# 004 — School accounts (organisations, shared quota, three roles)

Status: **planned, not built.** Decisions below were taken with the founder on 2026-08-12.

## What this is

A school buys one institution subscription and attaches its people to it. Those people study on the
school's quota instead of buying their own, and the person who paid can see how it is being used and
cap anyone who is burning too much of it.

Three roles, each strictly containing the next:

| role | Hebrew | can |
|---|---|---|
| admin | מנהל | everything a teacher can, plus: manage teachers, set per-member caps, transfer ownership, billing |
| teacher | מורה | open the school panel, invite and remove students, see usage |
| student | תלמיד | study on the shared pool; sees only their own usage |

## Decisions taken (do not relitigate without the founder)

**1. Topics only. The panel NEVER shows the text of anyone's conversation.**

The original request was for the admin to read students' messages. That was dropped in favour of
showing *what subjects* a student has been asking about and how much, never the conversations
themselves. This is the single most important decision in this document, for two reasons:

- *Legal.* Privacy policy 1.8 permits the OPERATOR to review conversations to improve the service. It
  says nothing about a third party — a school — reading them. Shipping that would have contradicted a
  published promise, required a 1.9 with its own notice period, and, because many students are
  minors, put the most sensitive category of personal data under Israel's Privacy Protection Law
  (amendment 13, in force since August 2025) in the hands of whoever bought a subscription.
- *Product.* The need behind the request is supervision — is this being used, and for learning? Topic
  and volume answer that. Message text answers a different question nobody asked, and a teacher who
  can read a student's private questions changes what the student is willing to ask. That would
  quietly damage the thing the product is for.

If content access is ever revisited it needs: a distinct in-product disclosure at join time, the
student's explicit acceptance, a privacy policy section, a written warranty from the school that it
holds parental consent for minors, and a per-open access log. Not a line in the terms.

**2. Joining is by INVITATION, accepted by the member. Never by an admin typing an ID.**

The ID is how an invitation is addressed, not how a link is completed. As originally specified, an
admin could type any user id in the system and attach that account — and a typo would attach a
stranger. Membership changes what quota a person spends and exposes their usage to someone else;
that cannot happen without them agreeing to it.

**3. A member cannot hold their own paid subscription — and we never cancel one for them.**

An invitation to an account with an active paid plan is REFUSED, showing the date it lapses. We do
not auto-cancel: that is touching someone's money, and it collides with the statutory cancellation
and refund rules already implemented in `app/plans.py`. The mirror case is blocked too — a current
member trying to buy a personal plan is stopped with an explanation and told to leave the school
first.

**4. Per-member caps ship in v1, not as a later feature.**

One student can spend a school's entire day in an hour. Every member gets a default cap that is a
fraction of the pool, which the admin can raise or lower. The admin is warned when the school passes
~80% of its daily pool — after it is exhausted, the warning has no value.

**5. Seats: up to 40 members per institution subscription.**

Chosen against the existing allowance: institution is ×40 the free tier (8M tokens/day), which
supports roughly 40–80 active students. Beyond 40 members the school buys another seat. Without this
a 1,000-pupil school buys one ₪199 subscription and every pupil starves.

**6. The operator panel gets a ROLE SIMULATOR, not user impersonation.**

The founder asked to be able to "see the states of every account type" from the operator panel. Two
different things hide behind that:

- *Role simulation* — render the app as an admin/teacher/student sees it, against a synthetic demo
  school. Answers "does the teacher panel look right", costs nothing, exposes nobody. **This is what
  we build.**
- *Impersonating a real user* — open a specific person's account and see their real data. This would
  be a complete bypass of decision 1: the panel would show, through the back door, exactly the
  conversation text we just decided no school administrator may see. **Not built.**

If a real support case ever needs the second, it is its own feature with the user's consent and a
log, not a switch on the operator panel.

## Data model

Three new tables. Nothing in the existing schema changes shape.

```
orgs            id, name, owner_id (the admin), plan, seats, created_at
org_members     org_id, owner_id, role, daily_cap, invited_at, accepted_at, invited_by
org_access_log  org_id, actor_owner_id, target_owner_id, action, at
```

- `org_members` rows exist from the moment of invitation, with `accepted_at` NULL. A pending row
  grants nothing — membership is `accepted_at IS NOT NULL`, checked in one place.
- `org_access_log` is written even though v1 shows no message text. It records who opened whose usage
  and when. Cheap now, and if the topic view is ever widened it is already there — an audit trail
  added after the fact cannot describe what happened before it existed.
- Quota resolution becomes: owner → accepted membership → org pool, falling back to the member's own
  plan when they belong to no org. It must live in ONE function, next to `plans.daily_tokens`, or
  personal and school quota will drift apart.

## Access control

**Do not reuse `app/api.py::_is_admin`.** That is an environment allowlist for the OPERATOR of the
whole service. School roles are per-org data and must be read from the database. Reusing that gate
would make every school admin an operator, or force operator ids into a school table; both are wrong.

Every school endpoint answers three questions in order: is the caller an accepted member of this org,
does their role permit this action, and is the target of the action in the same org. A missing third
check is how an admin of school A edits a member of school B.

Teachers do NOT get message topics for students by default — only aggregate usage. Topic visibility
is an admin capability the admin may grant to a named teacher. Least privilege: it costs nothing to
start narrow, and widening later is easy where narrowing after the fact is not.

## Scope

**v1** — org creation on institution checkout · invitation + acceptance · roles · shared pool with
per-member caps · usage view (counts, tokens, topics) · 80% warning · leave/remove · ownership
transfer.

**Explicitly out** — message text (decision 1), user impersonation (decision 6), per-student pricing,
cross-org anything.

## Open questions

- What does "topic" mean concretely — the intent (qa/lesson/halacha), the work the sources came from
  (Gemara, Halacha), or a label derived from the question? The first two are free from data we
  already record in `usage_events`; the third needs generation and therefore costs money per turn.
- Does removing a member delete their conversations? Proposed: no — the account and its history stay
  with the person, they simply revert to the free tier. The school bought quota, not the student's
  work.
- What happens to members when the school's subscription lapses? Proposed: everyone reverts to free,
  nobody is deleted, and the admin can re-subscribe to restore the pool.
