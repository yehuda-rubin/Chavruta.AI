<!--
  DRAFT for a lawyer's review - not in force, does not replace docs/legal/privacy-en.md.
  Written by Claude (not a lawyer) for FR-032 of specs/009-school-minors/spec.md. The Hebrew draft
  (privacy-he-draft.md) is the primary text; this is a short equivalent. [UNSURE] = unresolved point.
-->

# DRAFT: Changes to the Privacy Policy - Chavruta AI (pupils aged 12-17 via the school track)

> **Disclaimer.** Written by an AI system. **Not legal advice.** Not reviewed by a lawyer. Statute references are from
> `docs/MINORS_READINESS.md` (**[UNVERIFIED]**). Do not publish without a lawyer's sign-off.

**Proposed version: 1.12** (live: 1.11). Effective date: `[TBD]`. Sections touched: 1, 2, 3, 4, 5, 6, **7 (rewritten)**, 9, 11, 12, 13.

## Changes block (new, top of document)
> Changes in version 1.12: the Service opens to **pupils aged 12-17 on the school track** (Terms 1.16, sections 5, 5a, 5b). Adult use is
> unchanged. For minors: (1) signup stores **birth month and year, server-side**; (2) **a minor's messages, lessons, source sheets and feedback are never used for
> training, quality review or question harvesting - also after 18 - and are deleted 60 days after writing**; (3) teachers and the school see **crisis alerts only,
> never conversations**; (4) a minor's messages are scanned automatically for distress; (5) no marketing to minors; (6) answers for minors come only from an LLM
> provider designated as suitable for minors; (7) a plain-language summary for ages 12-17 is available in the Service.

## Section-by-section

**1 (What we collect) - was:** account details incl. "age confirmation (18+) and its time." **becomes:** account details incl. **birth month and year** (server-side; not changeable by the user or the school) from which minor/adult status and the date of turning 18 are derived. **Added:** school/parent links (who approved, when, no age visible to the school); **parent-consent proof for a minor without a school: the parent's email address, status (pending/approved/declined/expired/revoked), send time, decision time, and the parent's IP address and user agent at the moment of decision - used only to send and prove the consent request, never for marketing; no parent account needed. [LAWYER: retention period of this proof (suggested: while the account exists plus a legal-defence period `[X]`); data minimisation; may a parent's IP/user agent be collected.]**; an immutable "written as a minor" mark and deletion date on each message, lesson and source sheet; **crisis-alert records** (pupil ID, school, time, category, recipients, acknowledged - **no message text**); automatic distress scanning (phrase layer + classifier) before any answer; operator views of flagged minor content limited to category plus a redacted snippet without account ID. **[UNSURE: retention of alert records; whether the classifier runs in-house or at a provider; whether data on distress is "sensitive information" under Amendment 13.]**
The operator's inspection right for quality, improvement and training **does not apply** to minors' content.

**2 (Use) - added:** a minor's content is never used for training, tuning, evaluation, quality review or harvesting, permanently and without any switch; no marketing to minors and no marketing consent is requested.

**3 (External AI providers) - added "AI provider for minors":** answers for minors come only through a provider designated as suitable for minors, via a commercial API; if it is unavailable the request fails (no fallback). Provider: `[not chosen yet]`. Per the provider's terms it does not train on the content **[verify against Anthropic Commercial Terms]**; inputs/outputs are deleted after about 30 days; **content the provider automatically flags as a policy violation may be kept up to 2 years and classification scores up to 7 years**, i.e. beyond our 60 days **[from MINORS_READINESS s.3 - verify; LAWYER: compatible with minors' data? is ZDR needed?]**. We do not send the pupil's name, school or email to the provider **[verify in code]**; but personal details a child types into a message go as written.
**Important:** as of writing no provider is approved for minors. Nebius (current default) is unsuitable (Services Agreement s.4.1.6 treats minors' data as sensitive; service "not intended for under-18s"). This section cannot be true until a provider is chosen.

**4 (Sharing) - added:** for minors the sub-processor list is narrower (the minors' AI provider, hosting/database, authentication, system email; no payment or marketing processors) **[verify]**; the school receives crisis alerts (no text) and basic account data - **[LAWYER: legal basis for telling a teacher/counsellor about a child's distress without the parent's knowledge]**; nothing goes to authorities automatically - only by a written procedure, human decision and law (e.g. court order or immediate danger to life).

**5 (Retention) - added:** minors' messages, lessons, source sheets and feedback are deleted **60 days after writing**, regardless of activity or saved status **[UNSURE: 60 is the midpoint of the founder's 30-90 range; update here and in the child summary together]**. Open: telemetry/IP logs of minors; alert-record retention; age/link records.

**6 (Rights) - added:** a minor may view and ask to delete; a linked parent (with the child's approval) may correct birth month/year and switch content off, with no access to conversations; the school may remove a pupil and change content settings, but not see conversations or change age; age changes are logged. Closing the institution's account does not automatically delete pupils' accounts **[LAWYER]**. How a minor exercises access/correction rights against parents' rights **[UNSURE]**.

**7 - was:** "The Service is not intended for minors (18+ only; pupils are not users)." **becomes (rewritten) "Minors, pupils and schools":** 7.1 who may use (18+, and pupils 12-17 on the school track only; under 12 refused/closed); 7.2 age by declared month/year, unverified, server-side, correctable only by a linked parent or the operator (logged); 7.3 the school contracts, pays and attests it holds parental consent **[LAWYER: who is the database owner and who the holder/processor - likely the school owns, we process; needs a DPA; adjust section 11]**; 7.4 what we do not do (no training, no QA review, no marketing, no prices, no sale of data, no charges); 7.5 school sees alerts only, no conversations, lessons or age; 7.6 distress flow (fixed reply; ERAN, SAHAR, 100; alert without text; no automatic report) **[LAWYER: adequacy as notice under s.11 of the Privacy Protection Law]**; 7.7 **parental consent for a minor without a school**: no messages until a parent consents, via an active link to the parent's account or approval through an emailed link (valid 7 days); consent covers 7.4-7.6 and 60-day retention; the parent may revoke at any time by link, request access to what is held about the consent and the child, correct age, and ask for deletion of the child's account and of the proof; the child cannot revoke; the parent gets no access to conversations **[LAWYER: can a parent without an account exercise rights; how identified; may the proof be deleted when needed for legal defence]**; 7.7a turning 18; 7.8 plain-language summary (the policy remains the binding text) **[LAWYER]**; 7.9 under-12s: account closed, data deleted.

**9 (Transfer abroad) - added:** for pupils consent to transfer is given by the school (attesting parental consent); provider location `[TBD]` **[LAWYER: validity under the cross-border transfer regulations]**.

**11 (Database, purposes) - added purpose:** operating the Service for pupils on the school track, incl. distress detection and alerts. Database owner for school pupils `[TBD, see 7.3]`. **The earlier privacy-officer/sensitive-data assessment (no sensitive data, no systematic monitoring) no longer holds** at the new scope: possibly sensitive data (belief, mental state of minors) and systematic message scanning **[LAWYER: privacy officer, registration, DPIA; thresholds of 10,000 data subjects unverified]**.

**12 (Opt-out) - added:** minors are always excluded, with no switch, irreversibly.

**13 - added:** material changes concerning minors are notified to the school in advance **[UNSURE: parents?]**. Add a **public statement of compliance** with privacy and child-protection law (an expectation in the provider's guidelines) - wording only after legal advice **[LAWYER]**. Sections 8 and 10: no text change (verify no minor content in local storage; consider the Ministry of Education vendor security standard - not read).
