<!--
  Privacy Policy — recommended for legal review before going live.
  Operator: Yehuda Rubin · Jurisdiction: State of Israel.
  The in-app version is rendered from the same content (web/lib/legal.ts) — update both together.
-->

# Privacy Policy — Chavruta AI

**Version 1.9 · Effective 13 August 2026**

Changes in version 1.9: two clarifications, both of which widen your rights rather than narrow them.
**(a) Immediate deletion:** until now account deletion always ran after a grace period of about 30
days. You can now choose, at the moment of deletion, between deletion at the end of the grace period
(cancellable) and **immediate deletion** (not cancellable) — a user asked for this explicitly, and
rightly: a grace period exists to make an accidental click reversible, not to delay a deliberate
request (section 6). **(b) A deletion request stops section 2's use at once:** from the moment you
request deletion, your conversations are no longer included in quality review, service improvement or
model development — even though the data itself still exists until the grace period ends. Cancelling
the deletion restores the previous state (sections 6, 12).

Changes in version 1.8: a new section (12) has been added — **starting 10 August 2026, at 00:00**,
we may review conversation content (not only flagged messages, as today) and use it for internal
quality review, improving the Service, and developing or fine-tuning our own models by the operator
(section 2, and section 11 purpose 8) — distinct from what the model provider does with the data
(section 3, unchanged). **This applies only to conversations created from that date onward** — not
retroactively to existing conversations (section 5). In practice, review or use of content begins 24
hours later (11 August 2026), to give real time to exclude a conversation before anything is
actually read. You can exclude a specific conversation, or all of them at once with a single toggle
(new section 12). **There are now registered users on the Service**, so this update is also sent by
advance email notice — not only published here.

Changes in version 1.7: the AI model provider and the hosting provider are now **named — Nebius**
(sections 3, 4, 9) instead of being described only generically — Nebius both runs the Service itself
and generates the answers. It is now stated explicitly that its processing takes place in the
European Union (section 9). There is no substantive change to how processing actually happens —
this is a precision of who was already disclosed, not a new provider.

Changes in version 1.6: section 1 gained a disclosure of an **automatic, keyword-based scan** that
messages in the Service (questions and answers) go through, to catch unlawful, abusive, or
potentially defamatory content — the scan is **not** AI and does not analyze meaning, and it never
blocks/deletes/alters content automatically, only forwards a flagged message for our own manual
review. **The same update documents, for the first time,** the pre-existing mechanism letting you
flag an answer yourself — it had not previously been documented in this policy. A matching purpose
was added to section 11. There are no registered users yet, so no individual prior notice was
needed; the update takes effect from its publication date.

Changes in version 1.5: clarified that if the user points their own API key (see the Terms of Use)
at a provider and model other than the default, the custom base URL and model name are also not
collected or stored by us — exactly like the key itself (section 1).

Changes in version 1.4: added a reference to **Your Own API Key (Bring Your Own Key)** — see the
Terms of Use: if the user chooses to enter their own key, it is not collected or stored by us at all
(section 1), and in that case their questions are sent to the provider via their own account rather
than through our arrangement with it — that provider's own terms govern that data (section 3).

Changes in version 1.3: section 7 rewritten — **the Service is not intended for minors**,
registration requires an age confirmation, and we neither ask for nor need pupil data of any kind.
The Service builds teaching material for pupils, but **the pupil is not a user of the Service** —
the teacher is.

Changes in version 1.2: a new section **The Database, Its Purposes, and the Applicable Law**
(section 11) sets out the purposes of the database, refers to **Amendment 13** to the Protection of
Privacy Law, and records our assessment on appointing a privacy officer; it is now stated explicitly
that **there is no "no-training" path** (section 3) and that **we do not verify age** (section 7);
and the Service is **scoped to an audience in Israel** (Terms of Use, section 13). The contact
section is renumbered as section 12.

Changes in version 1.1: this policy now states the 90-day conversation retention window, itemises the
usage measurements recorded per request and the content that is deliberately not recorded, and states
that those measurements are detached from your identity when an account is deleted.

This policy explains what information Chavruta AI (the "Service", operated by Yehuda Rubin)
collects, how it is used, and your rights. Using the Service constitutes acceptance of this policy.
**Providing your data is not a legal obligation — it is a condition for using the Service** (e.g. an
email address for sign-in); sources you attach are provided voluntarily, at your choice.

## 1. What We Collect
- **Account details:** your email address, managed through the registration provider (Supabase). We do
  not see or store your password — it is stored and secured by the provider. Also recorded with the account are **your
  acceptance of the terms and your age confirmation (18+) given at registration, and their
  timestamps** — the record that the declaration was made.
- **Content you create:** your questions, conversation history, saved lessons, and sources you attach
  (text / PDF / Word).
- **Flagging messages for review — automatic and by you:** you can flag a given answer for our
  manual review (e.g. if you believe it mischaracterizes a real person). In addition, every message
  in the Service (question or answer) also goes through an **automatic, keyword-based scan only** —
  not AI, not meaning-based analysis — for content that may be unlawful or abusive (e.g. violence,
  content involving minors, self-harm), or that may pose a defamation risk toward a real person. In
  both cases, **the flag does not block, delete, or alter** content automatically; it only forwards
  the message for our own manual review, by reference to the existing message id (not by copying the
  content anywhere else).
- **Usage and measurement data:** to enforce quotas and improve the Service we record, for each
  request, **metrics only** — timestamp (including local hour and weekday), action type (question /
  explanation / comparison / halacha / chavruta / lesson building), language of request, tokens
  consumed, number of model calls, processing duration, whether sources were found and how many,
  number of files attached, and for a lesson — target audience, grade band and length. We use them to
  understand what needs improvement, what costs more, and at which hours the Service is busy.
  **We do not store in these records the content of the question, answer, sources or attached files**
  — only measurements. In addition, basic technical records are kept (request id, IP address) for
  security and rate limiting.
- **Local preferences:** language, theme and display settings are stored in your browser (localStorage).
- **Your own API key (if you choose to use one — see the Terms of Use):** the API key, a custom
  provider base URL and a custom model name are **not collected or stored by us at all** — they stay
  only in your browser and are sent to our servers only at the moment of actual use, to relay your
  request to the provider on your behalf.
- **Subscription & billing data:** if you purchase a subscription — your subscription status and period
  dates, and a reference (token) to the payment method held by the payment provider. **We do not see or
  store your full card number** — it is handled by the payment provider.

## 2. How We Use It
To operate the Service and generate answers; to associate your conversations and lessons with your
account; to enforce quotas; and to secure the Service and prevent abuse. We do not use your content
for advertising.

**In addition, and subject to the exclusion mechanism in section 12:** we may review conversation
content and use it for internal quality review, improving the Service, and developing or
fine-tuning models by the operator. This is **different** from section 3 (what the model provider,
Nebius, does with the data to generate an answer in real time) — this is about our own use, as the
operator, of content held with us. This use applies only to conversations from 10 August 2026
onward (section 5), and you can exclude a specific conversation or all of them from it.

## 3. Processing and Training by the Model Provider
To generate an answer, your question (and any source you attach) is sent to our AI model provider —
**Nebius**. **Nebius may use the data sent to it — your questions and attached sources — also to
improve and train its AI models**, subject to its terms. Therefore **do not enter sensitive,
confidential or personal information** you would not want processed, or used for model training, this
way.

**There is no "no-training" path on this Service — not on a paid plan and not on an institutional
account.** We say so explicitly so that you do not conclude otherwise: there is no setting you can
ask us to enable, and no tier that buys one. The rule in this section — what is not entered is not
sent — is the only protection that exists here, which is why it is written as a rule and not as a
recommendation. If we move to a provider that offers a non-training path, we will update this section
and give notice.

**If you choose to use your own API key** (see the Terms of Use, including the option to point it at
a provider and model other than the Service's default), your questions and attached sources are sent
to that provider using your own key and account — **not through our arrangement with it**. In that
case, that provider's own terms and privacy practices, as you accepted them directly when creating
the key, govern that data — not the arrangement described above.

## 4. Sharing
We do not sell your data. We use sub-processors only to run the Service: the registration provider
(Supabase), and the AI model provider **and** the hosting provider that runs the Service itself —
**both Nebius**. **For paid subscribers — the payment
provider (PayPlus) and the invoicing provider (Green Invoice)**, which process payment and billing
data. Study sources are retrieved from a Sefaria-based corpus subject to their licenses. We will
disclose information if required by law.

## 5. Retention
- **Conversations: kept for up to 3 months.** A conversation with no activity for 90 days is deleted
  automatically, with its messages. Any new message in the conversation resets the count — a
  conversation you keep returning to will not be deleted.
  **We recommend downloading and saving content that is important to you for the long term.**
- **Review and use for quality control, improvement, and model development (section 2)** applies
  **only** to conversations created from 10 August 2026 onward — not retroactively to earlier
  conversations. You can exclude a specific conversation from this, or all of your conversations
  with a single global toggle — see section 12.
- **Lessons you create: not deleted automatically.** They are your work product and are kept until you
  delete them or until the account is closed.
- **Measurement data** (section 1) is kept for trend analysis. On account deletion it is **detached
  from your identity** and remains as anonymous aggregate data only.
- **Billing records:** we are required by law to keep accounting documentation of payments (about 7
  years). This documentation is kept **without association to your identity** — amount, date and invoice
  number only — and continues to exist even after account deletion.
- Technical records are retained for a limited period for security.

## 6. Your Rights
- **Access and deletion:** you can view and delete your conversations and lessons at any time in the app.
- **Account deletion:** you can request account deletion from Settings, and choose between two
  options. **Deletion at the end of a grace period** (about 30 days) — the default, during which you
  can cancel it; it exists so that an accidental click is reversible. **Immediate deletion** — the
  data is erased at once, with no grace period and no way to cancel. In both cases all data
  associated with the account is permanently erased (as is the login, where configured).
- **A deletion request stops section 2's use immediately:** from the moment of the request — not at
  the end of the grace period — your conversations are no longer included in quality review, service
  improvement, or model development and fine-tuning. Cancelling the deletion brings them back in.
- **Correction:** you can update details in account settings.
- **Response times:** we will answer an access request within 30 days (extendable by a further 15 days
  as permitted by law). Following a deletion or correction, we will also notify parties to whom the
  data was disclosed in the preceding 3 years, where required by law.

## 7. The Service is not intended for minors
**The Service is for users aged 18 and over only** (Terms of Use, section 5). Registration requires an
explicit age confirmation, which is recorded with the account. **We do not knowingly collect personal
information from minors.** If we learn that an account was opened by a minor we will close it and
delete the information. If you know of such a case, contact us (section 13) and we will act.

**This is a declaration, not verification**, and we say so explicitly: registration is by email
address and we have no means of checking age. What exists is a clear scoping of the intended audience
and a deliberate statement by the user.

- **Schools and institutional accounts:** the Service builds teaching material **for** pupils — and
  **the pupil is not a user of the Service.** The person who operates it, enters the question and
  receives the lesson is the **teacher**, who is an adult. **We neither ask for nor need pupil data of
  any kind**, and there are no pupil accounts.
- **Hence the rule that remains:** as described in section 3, what is entered is sent to the model
  provider. **Do not enter identifying details of any person — pupils included.** The Service needs no
  identifying detail in order to work: a question in learning is a question about a source, not about
  a pupil. **Preparing a lesson for a third-grade class does not require any child's name.**
- **Marketing:** we do not direct marketing at minors and do not use their data.

## 8. Cookies and Local Storage
We use browser local storage to keep your preferences and to maintain your active session (session
token). We do not use third-party advertising or tracking cookies.

## 9. Transfer of Data Outside Israel
Some sub-processors (Supabase, and Nebius — both as the AI model provider and as the hosting
provider, processing within the European Union) process data outside Israel. The transfer is
made on the basis of **your consent** and subject to a **contractual undertaking** by the providers to
maintain a level of protection equivalent to that required under Israeli law and not to transfer the
data onward without authorization, in accordance with the Protection of Privacy Regulations (Transfer
of Data to Databases Abroad), 2001.

## 10. Security
We take reasonable measures — authentication, rate limiting, and encryption in transit — to protect
your information, in accordance with the Protection of Privacy (Data Security) Regulations, 2017. In
the event of a serious security incident we will act to notify the Privacy Protection Authority and
affected users as required by law. However, no method is 100% secure and we cannot guarantee absolute
security.

## 11. The Database, Its Purposes, and the Applicable Law
**Database owner and manager:** Yehuda Rubin, the operator of the Service. Contact details in section 13.

**Purposes of the database** — the information itemised in section 1 is collected and used for these
purposes only:
1. operating the Service and producing answers and lessons;
2. associating conversations, lessons and the subscription with your account;
3. enforcing usage quotas and preventing abuse;
4. billing, issuing invoices and meeting accounting obligations;
5. securing the Service;
6. detecting unlawful, abusive, or defamation-risk content, for our own manual review (section 1);
7. understanding aggregate usage patterns in order to improve the Service;
8. internal quality review, improving the Service, and developing or fine-tuning models by the
   operator — only for conversations from 10 August 2026 onward, and subject to the exclusion
   mechanism (section 12).

**We do not use the information for any other purpose and we do not sell it.** Use for a new purpose
would require an update to this policy and advance notice.

**Applicable law.** This policy is drawn up under the **Protection of Privacy Law, 5741-1981, as
amended by Amendment 13** (in force August 2025), and the regulations under it — the Data Security
Regulations (2017) and the Transfer of Data to Databases Abroad Regulations (2001), referred to in
sections 9 and 10.

**Privacy Protection Officer.** Amendment 13 requires appointing an officer in certain circumstances,
including large-scale processing of sensitive data or systematic monitoring. **In our assessment the
obligation does not apply at the current scale:** the Service holds no sensitive data as defined in
the Law, performs no systematic monitoring, and records measurements rather than content (section 1).
This is our assessment, it is revisited as the scale grows, and an appointment will be made if and
when the obligation arises.

## 12. Excluding Specific Conversations from Section 2's Use
The use described in section 2 (quality control, improvement, and developing or fine-tuning models)
applies **only** to conversations created from **10 August 2026** onward (section 5, section 11
purpose 8). Excluding a conversation does **not** affect how the conversation itself works — an
excluded conversation keeps working normally; it is simply not included in this use.

**Excluding a specific conversation:** every conversation has a "Don't use this conversation" toggle,
next to the pin and rename options. The default is that a conversation is **included**, unless you
mark it otherwise.

**Global exclusion:** Settings has an additional toggle that excludes **all** of your conversations at
once, for anyone who would rather not go conversation by conversation. This toggle overrides the
per-conversation setting.

**Requesting account deletion also excludes, with no toggle needed:** an account pending deletion
(section 6) is excluded from this use from the moment of the request — even though the data still
exists until the grace period ends. Cancelling the deletion cancels this exclusion too.

In practice, review or use of conversation content begins **24 hours** after the effective date —
that is, from **11 August 2026** — to give real time to mark an exclusion before anything is actually
read.

## 13. Changes and Contact
We may update this policy; the current version is always shown in the Service. For privacy questions:
rubinyehuda8@gmail.com
