<!--
  Lawsuit-exposure audit — NOT a legal opinion, and Claude is not a lawyer. This is an engineering-
  level sweep of the actual code + legal docs, cross-checked against real Israeli statutes, looking
  for what a "serial plaintiff" (a lawyer/claimant who scans small sites for statutory-damages
  violations that need no proof of harm) or an ordinary claimant could use. Written 2026-07-30.
-->

# Lawsuit-Exposure Audit — 2026-07-30

**Who wrote this and how:** Claude, by reading the actual current code (`app/api.py`,
`app/auth_supabase.py`, `src/chavruta/corpus/rights.py`, the `web/` frontend) and cross-checking
specific legal claims against primary sources (statute text, Creative Commons legal code) or
reputable Israeli legal commentary where the primary source wasn't reachable. Findings are graded
by whether they're a **fixable gap** (code/doc problem, has a concrete remedy) or an **inherent
risk** (a real category of exposure that no code change removes, and that a lawyer's judgment call
is what actually reduces it). This supersedes nothing in `REVIEW-2026-07-27.md` — it extends it.

---

## Already closed (context — see REVIEW-2026-07-27.md and its 2026-07-29/07-30 addenda)
Web accessibility (statement + `/accessibility` route, closes the 60-day cure-notice trigger),
anti-spam consent (opt-in marketing checkbox), Privacy Law / DPO thresholds (far under scale),
CC BY-SA Collection-vs-Adapted-Material reading, 18+ age scoping, refund/cancellation terms.

---

## Finding A — HIGH, fixable: terms/age consent is recorded but never enforced — ✅ FIXED 2026-07-30

**What's true today:** `SignIn.tsx` sends `terms_version`, `terms_accepted_at`, `age_confirmed_18`,
`age_confirmed_at` into Supabase `user_metadata` at signup. **`grep`-ing the entire backend
(`app/api.py`, `app/auth_supabase.py`) for these field names returns zero matches.** The backend
extracts only the JWT `sub` (user id) from a session — it never reads whether the metadata is
present, let alone rejects a request for its absence.

**Why this matters:** `NEXT_PUBLIC_SUPABASE_ANON_KEY` is, by definition, public (it ships in the
frontend JS bundle). Anyone can call Supabase's own signup REST endpoint directly with that key and
create a fully working account **without ever sending those fields** — bypassing both checkboxes
entirely, not just disabling JS. The Terms (§5) and Privacy Policy (§7) both state the age
confirmation "is a condition of registration" — today, nothing server-side makes that true. It's a
UI nicety, not a gate.

**Fix shipped:** `app/security.py::require_auth` now rejects a Supabase-mode request whose account
lacks both `age_confirmed_18` and a recorded `terms_version`, exempting `/me`/`/account` (same
pattern as the blocklist) so a gated account can self-serve out via the new
`web/components/ConfirmConsent.tsx` screen instead of hitting a dead-end 403 everywhere. No
grandfathering needed — the product hadn't launched publicly yet when this shipped, so there was no
pre-existing account population to reconcile.

---

## Finding B — MEDIUM, inherent risk (not a code bug): the liability-exclusion clause

Terms §3 disclaims all liability "to the maximum extent permitted by law" for AI-generated content
being wrong. Under the **Standard Contracts Law (חוק החוזים האחידים, 1982)**, a consumer-facing
take-it-or-leave-it contract's clauses can be reviewed and struck as **"מקפחות" (unfairly
prejudicial)** — and a supplier's blanket exemption from liability is explicitly one of the listed
categories courts and the Standard Contracts Tribunal scrutinize most. The "to the maximum extent
permitted by law" qualifier is the right drafting move (it self-limits rather than overclaiming a
blanket exemption that would clearly be struck), but it does **not** make the clause immune to
review — a court can still narrow it in a specific dispute. This isn't fixable by more code; it's a
drafting judgment call a lawyer should look at specifically, given it's one of the clauses this
product depends on most.

Source: [Standard Contracts Law, 1982 (Nevo)](https://www.nevo.co.il/law_html/law00/70311.htm),
[consumer-rights summary of prohibited clause categories](https://www.consumers.org.il/category/unfair-terms-in-standard-contract).

---

## Finding C — HIGH severity, genuinely unresolved (not fixable by code): defamation risk in AI output

**The single most legally-novel risk found in this audit — bigger than the CC-licensing question
already flagged.** Israel's Defamation Law (חוק איסור לשון הרע, 1965) §7א allows **statutory
damages up to ₪50,000 with no proof of harm** (doubled to ₪100,000 if malicious intent is shown;
practitioner commentary cites higher inflation-adjusted practical figures, roughly ₪80,000–160,000
in recent cases — treat the ₪50,000/₪100,000 statutory figures as the reliable ones and the higher
figures as commentary, not statute text) for a published statement capable of harming someone's
reputation.

**Why this product is exposed to it specifically:** the model answers open-ended questions,
including ones that could name real, identifiable people — historical authorities, but also living
or recently-deceased rabbis and scholars whose views, disputes, or biography a user might ask about.
A hallucinated or distorted claim about a real, identifiable person is exactly the shape of thing
this law targets, and unlike a human author, the operator doesn't review each answer before
publication.

**What's already mitigating this** (not eliminating it): the "AS IS"/no-warranty disclaimer, the
requirement that answers cite retrieved sources (grounding reduces, but does not eliminate,
fabrication about a person thinly documented in the corpus), and the "not a halachic ruling, verify
every source" framing throughout the Terms.

**What research could NOT resolve:** whether an Israeli court would hold a platform operator liable
for AI-generated defamatory output at all — this is **not yet settled case law** in Israel (search
for platform-liability-for-AI-content case law returned nothing conclusive; this tracks the same
"no known precedent" gap `NOTICE.md` already flags for the Sefaria-commercial-use question). This
is not something to try to code around — it's worth a direct question to a lawyer, and worth
keeping in mind as a real (if hard to quantify) tail risk as usage grows, especially if the product
is ever asked about controversial or living figures at scale.

Sources: [Defamation Law overview — Wikipedia](https://he.wikipedia.org/wiki/%D7%97%D7%95%D7%A7_%D7%90%D7%99%D7%A1%D7%95%D7%A8_%D7%9C%D7%A9%D7%95%D7%9F_%D7%94%D7%A8%D7%A2), [statutory-damages summary](https://www.shlomiweinberg.co.il/blog/defamation-claim-without-proof-of-damage/).

---

## Finding D — LOW, operational not legal: data-access requests are a manual process

Privacy Policy §5 promises a response to a "בקשת עיון" (data access request) within 30 days. There
is no self-service "export all my data" endpoint — but conversations and lessons are already
viewable/deletable in-app, which covers most of what Article-13-style access rights ask for, and a
manual, human-handled response to an emailed request is legally sufficient at this scale. This is
not a code gap; it's a reminder that if such a request ever arrives by email, **a person has to
actually notice and answer it within 30 days** — worth keeping in mind as the only "operational,"
not technical, promise in the policy.

---

## Finding E — already known, restated for completeness

PayPlus's refund call and Green Invoice's credit-note (type 330) have never run against a live
account (see `app/billing/payplus.py`, `REVIEW-2026-07-27.md` point A). Irrelevant while the launch
stays fully free with billing unconfigured (per the 2026-07-30 decision in
[[hosting-and-llm-cost-decisions]]) — re-verify the first time a real charge and a real refund
actually happen.

---

## What this audit did NOT find
No evidence of: third-party tracking cookies, sale of user data, undisclosed sub-processors, a
missing cancellation mechanism, an unenforceable coupon/refund flow, or a CC-license attribution
gap — the attribution mechanism (`src/chavruta/corpus/rights.py`) already does TASL-style credit
per source, states the CC BY/BY-SA deed URLs, and explicitly notes reproduction is unmodified
(satisfying CC BY 4.0 §3(a)'s "indicate if modified" condition) — this held up well under scrutiny.
