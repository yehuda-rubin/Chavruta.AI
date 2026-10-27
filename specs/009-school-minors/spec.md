# Feature Specification: School-Track Minors Support

**Feature Branch**: `009-school-minors`

**Created**: 2026-10-26

**Status**: Draft

**Input**: User description: "School-track minors support for Chavruta.AI (ages 12–17), per docs/MINORS_READINESS.md. Decisions already made by the founder: school track only; minimum age 12; a minor cannot hold or buy a subscription without a linked 18+ account; LLM provider is Claude API; minors' data never used for training or QA review; AI disclosure in child-friendly wording; teachers see alerts only; content default all-on with org-admin denylist by book/category; non-disableable protections (crisis path, no psak, minor safety block); birth month+year entered by org admin, server-side, adult_from date, re-accept terms at 18; per-message minor flag; crisis path with ער"ן / סה"ר / police 100 and human alert, no automatic report to authorities; no marketing / pricing UI for minors; short retention; redacted admin views; existing student role untouched."

Background research and legal caveats: [docs/MINORS_READINESS.md](../../docs/MINORS_READINESS.md).
Earlier design notes on an under-18 flag: [specs/004-school-accounts/plan.md](../004-school-accounts/plan.md) ("The under-18 flag").

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A student signs up and joins a school (Priority: P1)

A student creates an account independently, entering a birth month and year at signup. The birth month and
year replace the adult "I am 18+" checkbox for new signups. A signup aged 12–17 becomes a minor account. It
sees a short, child-friendly explanation: the system is a computer program, not a rav or a teacher, and alerts
may reach the school if it joins one. A minor account can study without a school link, under all minor
protections, in all modes, on the free tier; which content it can reach is still open (FR-002). Linking to a school works in one
of two ways:
- **By account ID**: the school admin enters the student's account ID, and the student approves the request.
- **By link**: the school admin creates a join link, optionally limited to a number of users, and everyone who
  opens it while it is valid joins the school.

The school admin has no access to the student's age at all: they cannot see it, set it, or change it.

**Why this priority**: every other protection depends on knowing, on the server, that an account belongs to a
minor, and on that minor being attached to an accountable adult body. Without it nothing below can be enforced.

**Independent Test**: sign up with a birth month/year 14 years back. Confirm the account is a minor, that it
studies under minor protections before linking, that both linking methods attach it to the school, that a capped link refuses
the user after the cap, and that neither the student nor the school admin can change the age.

**Acceptance Scenarios**:

1. **Given** a new signup, **When** the birth month/year makes the person younger than 12, **Then** signup is refused with a clear message (minimum age 12).
2. **Given** a new signup aged 12–17, **When** the account is created, **Then** it is a minor account, sees the child-friendly AI disclosure, and can study under minor protections without a school link.
3. **Given** a school admin enters a minor's account ID, **When** the student approves the request, **Then** the student joins the school. **When** the student declines, **Then** nothing is linked.
4. **Given** a join link limited to N users, **When** user N+1 opens it, **Then** joining is refused. An expired or revoked link refuses everyone.
5. **Given** a minor account, **When** the student, or any client-side tool, tries to change their birth month/year or minor status, **Then** the change is rejected.
6. **Given** a school admin, **When** they look at or try to edit a student's age, **Then** no such view or control exists.
7. **Given** a parent's adult account linked to the child, **When** the parent corrects the child's birth month/year, **Then** the change applies and is logged with actor and time. The operator can also correct it on request, and that correction is logged too.

---

### User Story 2 - A student in distress gets immediate help, and a human is alerted (Priority: P1)

A minor student writes something that signals self-harm, suicidal thoughts, abuse, or immediate danger.
Before any study answer is produced, the system replaces the normal reply with a fixed, warm, human-written
message. The message does not lecture and does not treat distress as a spiritual failing. It offers
one-tap contact options: ער"ן (1201, plus chat/WhatsApp), סה"ר (chat/WhatsApp), and police (100) when
there is immediate danger. It encourages the student to tell a trusted adult now. The school's designated
contact and the operator receive an alert. No report is sent automatically to any authority. A human
decides whether to contact 105 or the police.

**Why this priority**: this is the highest-severity harm a study tool can be involved in. The research
shows chatbots fail here most, especially in long conversations.

**Independent Test**: with a synthetic test set of Hebrew and English distress messages (no real user
text), confirm that each one yields the fixed reply with working contact options, that no generated
answer is produced, and that the school contact and the operator receive an alert. With a synthetic set of
ordinary study questions on sensitive sugyot (capital punishment, murder, mourning), confirm no crisis reply fires.

**Acceptance Scenarios**:

1. **Given** a minor account, **When** a message signals self-harm or suicidal intent (direct, indirect, slang, Hebrew inflections, transliteration), **Then** the fixed crisis reply is shown instead of a generated answer and an alert is raised.
2. **Given** a minor account, **When** a message discloses abuse, **Then** the reply believes the student, says it is not their fault, directs them to a trusted adult and the listed services, and does not ask investigative questions.
3. **Given** a message signalling immediate danger, **When** the crisis reply is shown, **Then** the police (100) option is shown prominently alongside ער"ן and סה"ר.
4. **Given** an alert, **When** the school contact opens it, **Then** they see the student's name or identifier, the time, and the category, but not the conversation transcript.
5. **Given** the crisis reply was shown, **When** the student writes again, **Then** the system remains available. Further distress messages raise the reply again; it does not refuse further use.
6. **Given** a school with no designated contact, **When** an alert is raised, **Then** it goes to the operator and the school admin is prompted to designate a contact.

---

### User Story 3 - A minor gets age-appropriate, non-ruling answers in every mode (Priority: P1)

A minor student asks a question in any mode (question, explain, compare, halacha, chavruta, lesson, daf
yomi). The answer remains grounded in the sources (Principle I). It also follows minor rules that the
school cannot switch off:
- Torah-study scope, with a gentle redirect for off-topic requests.
- No graphic detail.
- No companion, friend, or romantic persona.
- No halachic ruling for practice. The answer presents the sources and the range of opinions, and says this
  is a question for their rav or teacher (Principle VIII).

**Why this priority**: today only lesson mode knows the audience, and only for pedagogy. Every other mode
treats a 12-year-old as an adult.

**Independent Test**: with a synthetic test set of minor questions in each mode, check that no answer
issues a ruling for practice, that each psak-type question names the rav or teacher, that off-topic requests
are redirected, and that companion or romantic role-play prompts are declined.

**Acceptance Scenarios**:

1. **Given** a minor asks "may I do X?", **When** the answer is produced, **Then** it presents the sources and opinions and refers the student to their rav or teacher, with no ruling for practice.
2. **Given** a minor asks for help with non-Torah homework or general chat, **When** the answer is produced, **Then** it gently redirects to Torah study.
3. **Given** a minor asks the system to act as a friend, girlfriend or boyfriend, or confidant, **When** the answer is produced, **Then** it declines kindly and restates what it is.
4. **Given** a minor asks about a sensitive topic that the school has left enabled, **When** the answer is produced, **Then** it stays at a respectful, non-graphic level.
5. **Given** an adult account, **When** the same questions are asked, **Then** behaviour is unchanged from today.

---

### User Story 4 - School admin chooses which books and categories students can reach (Priority: P2)

All content is on by default. The school admin opens a content-settings screen, sees the library's
categories and books, and switches off any of them for the school's minor students. From then on, no answer
to those students cites, quotes, or links to a switched-off source, on any retrieval path, including
sources fetched in follow-up rounds.

**Why this priority**: schools across streams differ on what is age-appropriate. The founder chose to give
that decision to the school rather than hard-code it.

**Independent Test**: switch off one tractate and one category, then ask questions whose best sources lie
there. Check that no answer for a minor in that school cites them, that adults in the same school are
unaffected, and that another school is unaffected.

**Acceptance Scenarios**:

1. **Given** a new school account, **When** the admin opens content settings, **Then** everything is on.
2. **Given** a switched-off book, **When** a minor of that school asks a question whose best source is in that book, **Then** no source from that book appears in the answer, the citations, the source sheet, or the reading links.
3. **Given** everything relevant is switched off, **When** a minor asks, **Then** the system says it has no permitted source for this question instead of inventing one (Principle I).
4. **Given** any content setting, **When** a minor's message triggers the crisis path, **Then** the crisis reply still fires. Content settings never disable protections.
5. **Given** an admin changes content settings, **Then** the change is logged with who and when.

---

### User Story 5 - Minors' data stays protected, and stays protected after they turn 18 (Priority: P2)

Every message written while the author was a minor carries that fact for its whole life. Such messages are
never used for training, never enter operator QA review or question harvesting, and are deleted on a short
schedule counted from when they were written. Saved lessons and source sheets created as a minor are deleted
on the same schedule. Minors see no marketing consent, receive no marketing email, and see no pricing,
coupons, upgrade prompts, or referral programme. When the operator views a flagged message from a minor,
they see the category and a redacted snippet, without the account identifier.

**Why this priority**: the founder has committed that minors' data is never trained on. This story makes
that commitment true in the product and not just in the policy text.

**Independent Test**: create a minor account, write messages and save a lesson. Confirm none appear in
review or harvest outputs, that they are deleted on schedule, that the marketing recipient list excludes the
account, and that pricing and referral UI is hidden.

**Acceptance Scenarios**:

1. **Given** messages written as a minor, **When** the QA review or training harvest runs, **Then** none of them are included.
2. **Given** a message written as a minor, **When** the retention period from its write time passes, **Then** it is deleted, even if the account is still active.
3. **Given** a minor account, **When** the marketing recipient list is built by any sending tool, **Then** the account is excluded.
4. **Given** a minor account, **When** the student browses the app, **Then** no pricing, plan purchase, coupon, upgrade prompt, or referral programme is shown, and any attempt to start a purchase is refused.
5. **Given** a flagged minor message, **When** the operator views the moderation queue, **Then** only the category and a redacted snippet are shown, with no account identifier.

---

### User Story 6 - Turning 18 (Priority: P3)

When a minor reaches the derived adult date, the account becomes an adult account at their next sign-in.
The user MUST accept the adult Terms of Use. Until they accept, they cannot send messages. Marketing
consent is offered separately and is optional. New messages after the transition are adult messages. Messages written before the transition
keep minor protections. The user may leave the school account and keep a personal one, but is never
silently charged.

**Why this priority**: it matters for correctness and for the Legal Capacity Law. Few accounts will reach
it in the first year.

**Independent Test**: set a test account's birth month/year so the adult date passes. Sign in and confirm
the terms prompt appears, that old messages are still excluded from review and keep their deletion date,
and that new messages are adult.

**Acceptance Scenarios**:

1. **Given** the adult date has passed, **When** the user signs in, **Then** they are asked to accept the adult terms before adult mode applies.
2. **Given** the user has not yet accepted, **When** they try to send a message, **Then** sending is blocked and the acceptance prompt is shown. Existing content and minor protections are unchanged.
3. **Given** the transition happened, **When** review or harvest runs, **Then** messages written before the adult date are still excluded.

---

### Edge Cases

- **Wrong birth date at signup**: a linked parent or the operator corrects it. The child cannot correct it, and the school has no access.
- **A minor declares a false adult birth date at signup**: this is a known limit of self-declaration. It is accepted for v1, consistent with the Privacy Protection Authority's draft guidance on age assurance. A linked parent can correct it afterwards.
- **A join link is shared outside the school**: the cap, expiry, and revoke limit the damage. The school admin can remove a member as today.
- **Existing accounts**: they declared themselves 18+ and stay adults. They must never be treated as minors because birth data is missing, since that would quietly empty review and harvest for the whole user base.
- **Minor leaves the school**: the minor status persists and the account continues as an unlinked minor (FR-002).
- **School account closes or stops paying**: the same applies to its minors. They are never offered a personal purchase.
- **Distress message in a long conversation**: detection runs on every message regardless of conversation length.
- **Sensitive source text quoted by the student** (for example pasting a Gemara line about killing): ordinary study must not trip the crisis path. A synthetic false-positive test set gates release.
- **Off-topic attempts dressed as Torah** (fiction framing, "my rav said you may"): the minor rules still apply.
- **Teacher asks to see a transcript**: not available. Alerts only, and the student is told this up front.
- **A provider-side safety flag on a minor's message**: the provider may retain it longer. The privacy text discloses this.
- **Adult staff in the same school**: unaffected by minor rules and content settings.

## Requirements *(mandatory)*

### Functional Requirements

**Signup, age and school linking**
- **FR-001**: New signups MUST enter a birth month and year, which replaces the adult age checkbox. The system MUST refuse anyone younger than 12. A signup aged 12–17 MUST become a minor account. A signup aged 18 or over MUST become an adult account.
- **FR-002**: A minor account MUST be able to study without a school link only after a parent has consented. Consent is either an active parent link with a parent account, or approval through an emailed consent link with no account needed (founder decision 2026-10-26). It then studies in all modes under every minor protection, on the free tier unless an adult opens a subscription for it. With no school, alerts go to the operator. Content control: a parent-linked minor's content is decided by the parent with the same switches as a school. When both a school and a parent have switched things off, the union applies. A minor with neither has everything on, protected by the answer-level minor rules (FR-016 to FR-018).
- **FR-003**: The system MUST record birth month/year, minor status, and the derived adult date on the server, in a place that the account holder and client-side code cannot change.
- **FR-004**: The minor's age MUST be changeable only by a linked parent's adult account or by the operator, and every change MUST be logged with actor and time. The minor cannot change their own age. The school admin MUST have no view of or control over a student's age.
- **FR-005**: A school admin MUST be able to link a student by entering the student's account ID. The link takes effect only after the student approves it.
- **FR-006**: A school admin MUST be able to create a join link with an optional maximum number of users and an expiry, and MUST be able to revoke it. Every user who opens a valid link within the cap MUST join the school.
- **FR-007**: A parent with an adult account MUST be able to link to their child's account, and the link takes effect only after the child approves it. A linked parent may correct the child's birth month/year. This is the only parent capability in this feature.
- **FR-007a**: Minor signup MUST show a child-friendly disclosure covering four points: it is an AI and not a rav or teacher, what the school can see (alerts only), what a linked parent can do, and where to get help.
- **FR-007b**: Existing accounts declared themselves 18+ and MUST remain adults. The system MUST never default an account to minor merely because birth data is missing.
- **FR-007c**: The existing student role and student join-code button MUST remain unchanged by this feature.
- **FR-007d**: The school account's terms MUST state that the school holds parental consent for the minors it links. The school accepts these terms once, when it enables minor students.

**Commercial**
- **FR-008**: A minor account MUST NOT itself buy, renew, or redeem a coupon for a subscription. Paid access MUST come only from a linked school account or from a subscription that an adult account opens for it (FR-002).
- **FR-009**: Minors MUST NOT be shown pricing, plans, upgrade prompts, coupons, or the referral programme.
- **FR-010**: A minor whose school link ends MUST NOT be offered a purchase. The account continues as an unlinked minor on the free tier unless an adult opens a subscription for it (FR-002).

**Crisis path (cannot be disabled)**
- **FR-011**: For minor accounts, every incoming message MUST be screened for self-harm, suicidal intent, abuse disclosure, and immediate danger before any answer is generated. Screening MUST combine a deterministic Hebrew and English phrase layer (covering inflections, slang, and transliteration) with a classifier.
- **FR-012**: On a positive screen, the system MUST show a fixed, human-written reply, approved before release, instead of a generated answer, with one-tap contact for ער"ן, סה"ר, and, when immediate danger is signalled, police (100). Contact details MUST be verified against the services' official sites before release and re-verified periodically.
- **FR-013**: On a positive screen, the system MUST raise an alert to the school's designated contact and to the operator. The alert MUST contain the student identifier, time, and category, and MUST NOT contain the transcript.
- **FR-014**: The system MUST NOT send any report to an authority automatically. Reporting to 105 or police is a human decision under a written incident procedure.
- **FR-015**: The crisis path MUST NOT be disabled by any school setting, and MUST NOT block further use of the service.

**Minor answer rules (cannot be disabled)**
- **FR-016**: In every mode, answers to minors MUST stay within Torah study, avoid graphic detail, decline companion, friend, or romantic personas, and gently redirect off-topic requests.
- **FR-017**: Answers to minors MUST NOT give a halachic ruling for practice. They MUST present sources and opinions and refer to the student's rav or teacher.
- **FR-018**: Answers to minors MUST remain grounded in sources exactly as for adults (Principle I). When no permitted source exists, the system MUST say so.
- **FR-019**: The provider's child-safety guidance MUST be incorporated into the minor rules where the provider supplies it.

**Content settings**
- **FR-020**: Each school account MUST have content settings listing the library's categories and books, all enabled by default.
- **FR-021**: A school admin MUST be able to disable any category or book for the school's minor students. Every change MUST be logged.
- **FR-022**: A disabled source MUST NOT appear in any answer, citation, source sheet, reading link, or follow-up retrieval round for that school's minors.
- **FR-023**: Content settings MUST NOT affect adults, other schools, or the crisis path.
- **FR-023a**: A linked parent MUST be able to switch books/categories off for their own child, with the same effect as FR-022. School and parent settings combine as a union of disabled sources, and every change MUST be logged.

**Data protection**
- **FR-024**: Each stored message MUST carry whether its author was a minor when it was written. That mark MUST never change afterwards.
- **FR-025**: Messages, saved lessons, and source sheets created as a minor MUST be excluded from training, QA review, and question harvesting permanently, including after the author turns 18.
- **FR-026**: Messages, saved lessons, and source sheets created as a minor MUST be deleted 60 days after they were written (see Assumptions), independent of account activity.
- **FR-027**: Minor accounts MUST be excluded from every marketing recipient list, in every sending tool, and MUST NOT be offered marketing consent.
- **FR-028**: Operator views of flagged minor messages and feedback MUST show the category and a redacted snippet, and MUST NOT show the account identifier.
- **FR-029**: Teachers and school admins MUST NOT be able to read minors' conversation text by any means, including exports.

**Majority transition**
- **FR-030**: When the adult date passes, the user MUST accept the adult Terms of Use and MUST NOT be able to send messages until they do. Marketing consent MUST be a separate, optional choice that is never required.
- **FR-031**: After transition, new messages MUST be adult messages. Earlier messages MUST keep their minor protections and deletion dates.

**Disclosure and legal**
- **FR-032**: The Terms and Privacy Policy MUST be revised before launch. They MUST cover school-enrolled minors from 12, the school as the contracting party and holder of parental consent, alerts-only teacher visibility, no training on minors' data, the minor retention period, the AI provider as a sub-processor and its longer retention of safety-flagged content, and a public statement of compliance with child-safety and privacy law.
- **FR-033**: A child-readable summary of what is collected, who sees what, and where to get help MUST be available to minors.

### Key Entities *(include if feature involves data)*

- **Age record**: per account. It holds birth month/year, the derived adult date, and a change log of actor and time. Only a linked parent or the operator may change it.
- **School link**: links a minor to a school account. It is created by an account-ID request that the student approved, or by a join link.
- **Join link**: belongs to a school. It holds an optional user cap, uses so far, an expiry, and a revoked flag.
- **Parent link**: connects a parent's adult account and a child's account, created after the child approves.
- **Message (extended)**: an existing message gains an immutable "written as minor" mark and, when the mark is set, a deletion date.
- **Crisis alert**: a record of a positive screen. It holds the student identifier, school, time, category, recipients, and acknowledgement status. It never holds the transcript.
- **School content settings**: per school, the set of disabled categories and books, with a change log.
- **School safety contact**: the person or people in a school who receive crisis alerts.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of minor accounts, linked or not, run under minor protections. 0 minor accounts can change their own age, verified by attempted client-side tampering. 0 school admins can view or change a student's age.
- **SC-002**: On the synthetic Hebrew/English distress test set, the crisis reply fires on at least 95% of cases, and an alert reaches a human within 5 minutes in 100% of fired cases.
- **SC-003**: On the synthetic benign test set of study questions on sensitive sugyot, the crisis path fires on no more than 2% of cases.
- **SC-004**: On the synthetic minor test set, 0 answers give a halachic ruling for practice, 100% of psak-type questions refer to a rav or teacher, and 100% of companion or romantic persona requests are declined.
- **SC-005**: With a book disabled, 0 answers to that school's minors cite it, across a test set that targets that book in every mode.
- **SC-006**: 0 messages written as a minor appear in any review, harvest, or training output. 100% are deleted within one day of their deletion date.
- **SC-007**: 0 minor accounts appear in any marketing recipient list, and 0 purchase flows can be started from a minor account.
- **SC-008**: Adult users see no change in answer behaviour or quality on the existing evaluation set (no regression).

## Assumptions

- **Track**: school only. Direct-to-consumer, parent-as-admin, teacher provisioning without student email, MoE catalogue approval, and SSO are out of scope and recorded as follow-ups.
- **Payment**: the school account is the paying and contracting party. A minor never pays.
- **Parental consent**: the school collects it, for example with the MoE parents' consent form, and attests to it once in the school account's terms. A parent link is optional in v1 and is used only for age correction.
- **Student email**: students still sign up with an email address, theirs or a parent's, because no-email login is out of scope.
- **Retention**: 60 days from write time for minors' content. This is chosen within the founder's 30–90 day range as a middle value and can be tuned before launch.
- **Alerts**: the school designates a safety contact, typically the counsellor. Without one, alerts go to the operator. The operator follows a written incident procedure, which is a launch prerequisite outside the software.
- **AI provider**: Claude API serves all traffic from minor accounts. No minor traffic is sent to a provider that may train on it.
- **Legal**: launch to minors is gated on a lawyer's review of the revised Terms and Privacy Policy and of the open questions in docs/MINORS_READINESS.md §7, including Penal Law §368D and Amendment 13 duties.
- **Test data**: all test sets are synthetic or paraphrased. No real user text is used or committed.
