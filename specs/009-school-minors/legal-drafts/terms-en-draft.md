<!--
  DRAFT for a lawyer's review - not in force, does not replace docs/legal/terms-en.md.
  Written by Claude (not a lawyer) for FR-032 of specs/009-school-minors/spec.md. The Hebrew draft
  (terms-he-draft.md) is the primary text; this is a short equivalent. [UNSURE] = unresolved point.
-->

# DRAFT: Changes to the Terms of Use - Chavruta AI (pupils aged 12-17 via the school track)

> **Disclaimer.** Written by an AI system. **Not legal advice.** No sentence has been reviewed by a lawyer; statute references come from
> `docs/MINORS_READINESS.md` (secondary sources, **[UNVERIFIED]**). Do not publish without a lawyer's sign-off.

**Proposed version: 1.16** (live: 1.15). Effective date: `[TBD - not before lawyer sign-off and an approved minors LLM provider]`.
Sections touched: 1, 2, **5 (rewritten)**, **new 5a, 5b**, 6, 9, 10, 11, 12, 13. Sections 3 and 14: no text change (notes only).

## Changes block (new, top of document)
> Changes in version 1.16: the Service now also opens to **pupils aged 12-17, through the school track only** - a pupil linked to
> a school or educational institution that is the contracting and paying party and holds parental consent. Section 5 was rewritten;
> sections 5a and 5b were added. Main points: (1) signup asks **birth month and year** instead of an "I am 18+" box; (2) **a minor cannot
> buy a subscription** and sees no prices, coupons or marketing; (3) teachers and the school see **crisis alerts only, never the pupil's
> conversations**; (4) **a minor's messages are not reviewed for quality, not used for training, and are deleted 60 days after writing**;
> (5) on a message that signals distress the system shows a fixed reply with referrals, and sends an **alert without the message text** to
> the school's safety contact and the operator - **no automatic report to any authority**; (6) at 18 the user must accept the adult
> Terms before sending messages. Adult use is unchanged.

## Section-by-section

**1 (The Service) - was:** "...for study, research and lesson preparation." **becomes (added):** for pupils 12-17 on the school track the Service runs in an adapted mode (see 5a): Torah study only, no halachic rulings, no friend/companion role, and it states plainly that it is **a computer program, not a rabbi, teacher or person**.

**2 (Not a halachic ruling) - added:** for a minor the Service gives no practical ruling at all; it presents sources and views and refers the pupil to their rabbi or teacher.

**3 (Liability) - no change. [LAWYER]** Is the cap enforceable against a minor / a school acting for one? Do not add limits on liability for a minor's bodily or mental harm without an opinion.

**5 - was:** "Age - 18 and over only; not for minors; registering a minor is a material breach; institutions must not give pupils access; indemnity."
**becomes (rewritten):**
- 5.1 Groups: (a) adult 18+; (b) pupil 12-17 on the school track (5a); (c) a minor 12-17 **without** a school link may use the Service only after a parent or guardian consents (5.1a).
- 5.1a Parental consent for an unlinked minor: until consent the minor cannot send messages. Consent is either (i) an active link between a parent's adult account and the child's account, approved by the child, or (ii) approval through a link emailed to the parent address the minor supplied (no parent account needed; link valid 7 days). The **parent is the consenting party** for an unlinked minor; the school remains the party for a school-linked minor. Consent covers: use as a computer program, not a rabbi or teacher; the minor answer rules; collection and 60-day retention; no training or quality review; distress screening and alerts to the operator (and to a school safety contact if the minor later joins a school); no automatic report to authorities; no purchases or marketing. The parent may **revoke at any time** via a link in the email; the minor cannot. After revocation the minor cannot send messages until new consent or joining a school. The parent address must not be the child's own, and an email address does not prove the approver is the parent. **[LAWYER - key question: is consent by emailed link, without identity verification or a parent account, adequate parental consent for a 12-17 user under the Legal Capacity and Guardianship Law and the Privacy Protection Law (Amendment 13)? Is further verification needed? Evidentiary value of IP/user-agent/time? Divorced or disagreeing parents? A child entering a fake "parent" address?]**
- 5.2 Minimum age 12. Under-12 registration is refused; such an account is closed and data deleted.
- 5.3 Age is by declared birth month/year; we do **not** verify age. Only a linked parent or the operator may correct it (logged); the pupil and the school cannot.
- 5.4 A minor may not buy, renew, redeem a coupon or pay.
- 5.5 Narrow institutional indemnity only for pupils added **outside** the 5a track. **[UNSURE - possibly an unfair term; LAWYER]**

**5a (new) - Pupil aged 12-17 on the school track:**
1. The school is the contracting and paying party; the pupil is not party to a payment contract.
2. The school represents, once, that it holds parents'/guardians' consent for each pupil it adds (e.g. the Ministry of Education parents' consent form) and will produce a copy on request. **[LAWYER: is a one-off school attestation sufficient parental consent?]**
3. Joining: the pupil approves a school's request by account ID, or opens a capped/expiring join link. The school cannot see or set age.
4. Teachers/school see crisis alerts only - never messages, questions, lessons or answers, by any means including export.
5. The school may switch off books/categories; a linked parent may too; a source disabled by either is disabled. Neither affects the crisis path or the minor answer rules. **[UNSURE: default "everything on" includes sensitive tractates; legal question on harmful publication to minors.]**
6. Distress: fixed reply, referral to ERAN, SAHAR and, if immediate danger, police (100); alert (pupil ID, time, category - no text) to the school safety contact and the operator; **no automatic report to authorities**; the system can err both ways; duties of adults under law remain. **[LAWYER: Penal Law s.368D.]**
7. Minor answer rules (cannot be switched off): Torah only, no graphic detail, no companion/romantic persona, no practical ruling, refer to rabbi/teacher.
8. No marketing to minors. 9. A linked parent may correct birth month/year and switch content off; no access to conversations.
10. Minors' requests go only to an LLM provider designated as suitable for minors (12.3).
11. If the school ends the contract or removes a pupil, the account stays free-tier only with no purchase option and continues only if parental consent exists under 5.1a. **[UNSURE: whether use pauses until then; suggestion: yes.]**

**5b (new) - Turning 18:** at next sign-in the user must accept the adult Terms before sending messages; marketing consent is separate and optional; earlier minor content stays excluded from review/training and is deleted on its original schedule.

**6 - added:** a minor's messages, lessons, source sheets and feedback are **never** reviewed for QA, training or question harvesting (also after 18) and are **deleted 60 days after writing**; messages are scanned automatically for distress; operator views of flagged items are a category and a redacted snippet without account ID. **[LAWYER: consistency of "no review" with the alert and incident handling.]**

**9 - added:** a minor's data is not used by the operator for training and is sent only to the minors provider. **[LAWYER: provider training commitment - verify the Anthropic Commercial Terms.]** Content flagged by the provider may be kept by it longer than 60 days.

**10 / 11 - added:** minors cannot buy or redeem coupons and see no prices; paid access only through the school account; a school-ended or unpaid link leaves a free-tier account; a purchase made contrary to this is cancellable with refund under the Legal Capacity Law. **[UNSURE: exact refund wording.]** The "adult buys a subscription for a minor" mechanism is undecided (FR-002) and is deliberately omitted.

**12.3 (new) - Minors' AI provider:** notwithstanding the operator's freedom to route data between providers, minors' data goes only to the designated provider; if unavailable the request fails (no fallback). **Provider: `[not chosen yet]`.** As of writing **no provider is approved for minors**: the founder's decision is Claude API but contractual/legal approval is pending, and Nebius (current default) is unsuitable (its Services Agreement s.4.1.6 treats minors' data as sensitive).

**13 - added:** material changes affecting pupils are notified to the school in advance. **[UNSURE: parents? delivery? no response?]**

**14 - no change.** Arbitration/rabbinical-court option should not be offered to a minor. **[LAWYER]**

**Other:** gendered Hebrew; whether a minor can be suspended immediately (s.4); confirm that birth month/year is stored only server-side (not in Supabase); clarify in 11a that a minor cannot be a development helper; sync `web/lib/legal.ts`/`TERMS_VERSION` and force re-acceptance.
