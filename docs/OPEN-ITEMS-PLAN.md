# Open items — what is left, and how to close it

**As of 2026-08-14.** Everything here survived the 2026-08-14 deploy: each was found, verified
against the running system, and deliberately *not* fixed in that window, either because the fix needs
a schema change or because rushing it would have been worse than the defect.

Ordered by what it actually costs to leave alone — not by how alarming it sounds. Two of these are
cheap enough to do in an evening; one is a genuine piece of work and is the one that matters.

---

## A. The consent record is not evidence — `_has_consented` reads a field the user can write

**Severity: high, and it is legal rather than technical.** `app/security.py:153`:

```python
def _has_consented(payload: dict) -> bool:
    meta = payload.get("user_metadata") or {}
    return bool(meta.get("age_confirmed_18")) and bool(str(meta.get("terms_version") or "").strip())
```

`user_metadata` is the **user-writable** half of a Supabase identity. It is populated from the
client's own `signUp({ data })` and can be rewritten at any time by the signed-in user via
`updateUser({ data })` — a call this codebase itself exposes as `updateMetadata`
(`web/lib/auth.tsx:22`). The check's own docstring says it exists because "anyone could create a
working account via Supabase's own signup API and skip both checkboxes entirely" — and it then reads
the field that same API writes.

Anyone can `POST {SUPABASE_URL}/auth/v1/signup` with the public anon key and
`"data": {"age_confirmed_18": true, "terms_version": "1.12"}`, and the server will record them as
having accepted terms and confirmed 18+ without any UI having been shown.

**Why it matters more than it looks:** the whole 18+ posture rests on this record. If it is ever
needed — a minor's parent, a regulator, a dispute — "the account carried the flag" is not evidence of
anything, because the account holder sets the flag. And separately: **the app database holds no
consent record at all**, so acceptance is currently unauditable even in good faith.

### The fix

Record consent **server-side**, and gate on that.

1. **Schema 31** — three additive columns on `accounts`:
   `terms_version TEXT`, `terms_accepted_at TEXT`, `age_confirmed_at TEXT`.
   Additive only, same shape as the v30 migration; no rewrite of existing rows.
2. **`POST /account/consent`** — authenticated, writes the three columns from the verified `sub`.
   The client calls it once after sign-up and again whenever `TERMS_VERSION` changes.
3. **`_has_consented` reads the database**, not the JWT. Keep the route exemptions exactly as they
   are (`_ban_exempt`) so a user who has not consented can still reach `/me` and `/account/*` — and
   so can reach the consent route itself, which must be added to that exemption or the gate locks
   everyone out of the only route that opens it. *This is the step to get wrong; write the test first.*
4. **Backfill the three existing accounts** from Supabase's admin API (the service-role key can read
   `user_metadata`), and **record the provenance** — a `terms_source` value of `migrated` versus
   `server`. A backfilled record inherits the weakness of where it came from, and a record that
   quietly presents it as equivalent to a real one repeats the original mistake in a new table.
   With three accounts this is minutes, and all three are known people.

**Risk of the fix:** locking real users out of a running product. The gate currently 403s anything
outside the exemptions, so a bug here is immediately total. Ship it with the gate in **log-only mode
first** — write the record, log what *would* have been refused, change nothing — read a day of logs,
then enforce.

**Verify:** an account whose `user_metadata` claims consent but has no DB row is refused; the same
account is admitted after `POST /account/consent`; the consent route itself is reachable while
un-consented; and the three live accounts are unaffected across the deploy.

**Related, same area, worth doing at the same time:** the server never checks `email_verified` /
`email_confirmed_at`. If Supabase auto-confirm is on, disposable accounts each carry a free
200,000-token/day allowance that costs real money, with nothing bounding account creation. That is a
cost-control hole, not a privacy one, and it is one condition in the same function.

---

## B. BYOK DNS rebinding — the vetted address is not the address connected to

**Severity: medium. Partially closed 2026-08-14.** `security.validate_provider_base_url` resolves the
host and rejects any non-global address, which closes the direct cases (`127.0.0.1`, `10.0.0.0/8`,
`169.254.169.254`, `localhost`, `[::1]`). But it resolves the name *here* and the OpenAI client
resolves it again when it connects. A host that answers with a public address during validation and a
private one a moment later defeats the check entirely. The code says so rather than implying
otherwise — but saying so is not fixing it.

**The fix:** pin the connection to the address that was vetted. Resolve once, validate the resulting
IP, then connect to **that IP** with the original hostname carried in the `Host` header and SNI —
i.e. a custom `httpx` transport passed into the `OpenAI` client, since `openai` accepts an
`http_client`.

**Honest cost/benefit:** this is fiddly (TLS SNI plus certificate verification against the original
name), and the attacker must already be an authenticated account willing to run hostile DNS. The
direct cases are closed and those are the ones that get scanned for. **Recommendation: leave it, and
revisit if BYOK ever opens beyond a handful of users.** Written down so the decision is a decision.

---

## C. The API's full route map is public

**Severity: low, but the fix is ten minutes.** `_AUTH_EXEMPT` (`app/security.py:114`) includes
`/docs`, `/openapi.json` and `/redoc`, and `docker/nginx.conf` proxies `/api/` with a trailing slash
that strips the prefix — so `https://chavrutaai.org/api/openapi.json` serves the complete schema,
including the entire `/admin/*` surface that `_require_admin` otherwise hides by 404ing rather than
403ing. It grants no access; it removes all the discovery cost that the "404, never 403" convention
was built to impose.

**The fix:** construct `FastAPI(...)` with `docs_url`/`redoc_url`/`openapi_url` set to `None` when a
production flag is set, and drop the three from `_AUTH_EXEMPT` in that case. Keep them in local dev —
they are genuinely useful there, which is why they exist.

**Verify:** `/api/openapi.json` 404s in production and still works locally.

---

## D. The body-size cap is skipped on chunked requests

**Severity: low in the shipped topology.** `app/security.py` reads `content-length` and skips the
check when it is absent, which is exactly what a chunked request looks like. `QueryRequest.attachments`
allows 12 × ~4.4 MB of base64, and `_attachment_text` decodes and parses PDF/docx *before*
`_ATTACH_MAX_CHARS` can trim anything.

nginx's `client_max_body_size 3m` does enforce on chunked bodies, so today this only bites an
instance exposed directly — which is precisely the case the middleware's own docstring says it exists
for. **The fix:** count bytes as the stream is read and abort past the cap, instead of trusting a
header that is optional.

---

## E. Raw exception text reaches the client on async jobs

**Severity: low.** `app/jobs.py:81` stores `str(exc)` and `GET /jobs/{id}` returns it verbatim, so
provider errors, `sqlite3.OperationalError` text and filesystem paths can surface to a user. The rest
of `api.py` is careful about this — `/billing/checkout` deliberately maps to a clean 502. **The fix:**
map to a stable error code, keep the detail in the log against the request id.

---

## F. Decisions taken, recorded so they are not re-litigated

**`set_features` grants new capabilities to an accepted helper without asking again.** Judged
acceptable: the consent text covers "capabilities not yet open to everyone" as a category, and the
accepted-helper panel now displays the current grants, so nothing is hidden. **Revisit if** a feature
is ever added that changes what data is collected — that is a different consent, not a wider one.

**`MemberActionIn.daily_cap` has `ge=-1` and no upper bound**, so an org admin can set a member cap
above the school's own pool. `db.bump_pooled`'s ceilings still bound total spend, so it cannot exceed
what the school paid for; it only defeats the per-member control the admin themself set. Cosmetic.

**`/billing/limits` documents itself as public** but the app-wide `Depends(require_auth)` applies to
it. Comment is wrong, behaviour is right. Fix the comment when next in the file.

---

## Suggested order

Given the time available — yeshiva starts Sunday 2026-08-16 — the honest sequencing is:

1. **C** and **E** together: an evening, low risk, and C removes the map of the admin surface.
2. **A**, properly, in one focused sitting: schema, route, log-only deploy, read the logs, then
   enforce. Do not compress this into a late-night window; the failure mode is locking out every
   user at once. It is the only item here with legal weight.
3. **D** whenever the security middleware is next open.
4. **B** only if BYOK grows.

Nothing in this list is presently being exploited, and the two findings that were — a ₪49 charge
granting the ₪2,799 tier, and a self-service quota reset — went out on 2026-08-14 and are closed.

---

## G. The sources panel misses what the model used without marking it

**Decided with the operator 2026-08-14. Built, deployed, and rolled out to everyone 2026-08-14**
(`371cae0` — `_widen_citations_from_note`; `de28c1c` — the raw-ref chip fix; `89608d7` — the
retrieved_refs validation below). `CHAVRUTA_SOURCE_NOTE_OWNERS=*` on the VM as of 13:29 UTC.

Rollout was gated on real verification, not on the spec alone: the operator alone first, then a
correctness gap was found and fixed BEFORE widening it — `_widen_citations_from_note` validated a
named source against the whole corpus, not against what the model was actually shown that turn (see
`_fetch_refs`, no per-query scoping). Fixed by threading `retrieved_refs` through from `Answer`
(pipeline) to the widening call; a ref that resolves but was never retrieved is now logged
(`source_note_not_retrieved`) instead of becoming a citation. Verified on 12 real answers sent through
the actual `create_session` route after the fix: 12/12 carried the HHH block, and the new check caught
two real cases live — a halacha answer naming 5 real-but-never-retrieved refs, and a QA answer where
12 of 27 named refs didn't resolve in the corpus at all. Full detail: [[hhh-rollout-verification]].

No `pipeline.ask` contract change was needed for the base widening mechanism — `_fetch_refs()` already
existed. The retrieved-set check DID need one (`Answer.retrieved_refs`), found only once real data
showed the corpus-only check wasn't enough. Below is the original spec, kept for the record.

Measured on a real answer: the panel showed **16** sources, the model's own HHH list named **19**.
The panel is built from `enforce_citations`, which maps `[S#]` markers back to chunks — so a source
the model leaned on without writing a marker never reaches the reader. `Shadal on Numbers.22.2.2`
was one of the three missing from that answer.

This was the operator's original request and it was misread on the way in. It asked for "a list of
**all** the sources it used… and we put the sources on the side" — a question about WHICH sources
appear. It was built as a naming feature instead, and then removed as redundant once
`hebrew_display_ref`'s comma fix took the panel's Hebrew coverage to 98.5%. The naming problem was
real and is now solved; the coverage gap it was actually asked to close is still open.

**The design, which is not "display the list":**

1. Keep the HHH block (`CHAVRUTA_SOURCE_NOTE_OWNERS`) — it is the INPUT, not the output.
2. Match each of its lines back to a source that was actually RETRIEVED, on the ref. The model
   copies from a sources block formatted `<hebrew name> — <ref>` and often takes only half, so
   match on the ref substring and fall back to the Hebrew name.
3. A line that matches a retrieved source not already in `citations` → add it. The panel then shows
   everything the model used, and every entry is a real chunk: the list is an index into retrieved
   material, never a source of truth. This is what keeps a fabricated line from becoming a citation.
4. A line matching NOTHING retrieved → the model named a work it was not given. **Record it for the
   operator only** (`guard_findings`, the existing table and admin section — no user-facing change).
   That is the invention signal, and it is worth more as a measurement than the line is as a
   citation. Note what the first live runs produced: an author invented for the Ben Ish Chai, and a
   parasha called "איקה".
5. Do NOT re-add the grey panel box. It duplicated, in English, the sources listed beneath it.

**The one piece of plumbing this needs:** `enforce_citations`' `marker_map` holds every retrieved
source, and only the cited subset leaves the pipeline. Matching needs the full set at the API layer,
so `pipeline.ask` has to carry it out — that is a change to its contract and the reason this was
specified rather than rushed at the end of a long session.

**Verify with the model**, not around it: send the question through `/sessions/{id}/query` — the
route the app actually posts to — and confirm the panel count rises to meet the list. A check that
calls `pipeline.ask` directly cannot see a route-shaped gap, which is exactly how the HHH block
shipped gated on a route the app never calls.

---

## H. Tanakh and Mishnah are indexed WITH niqqud — this is likely the real cause of the base-pasuk recall gap

**Found 2026-08-14, investigating why `Job.31.2` doesn't surface for "חלק אלוה/אלוק ממעל" even after
the quotation floor (§ above, this session) and the de-euphemizer. Diagnosed only, not fixed — this
is a re-embedding job, not a code patch.**

The stored text for `Job.31.2` carries full niqqud + trop:
`וּמֶ֤ה ׀ חֵ֣לֶק אֱל֣וֹהַּ מִמָּ֑עַל וְֽנַחֲלַ֥ת שַׁ֝דַּ֗י מִמְּרֹמִֽים׃`. Checked across work types:
**Tanakh and Mishnah are stored vocalized; Halacha (`Shulchan_Arukh,_Orach_Chayim.1.1` sampled) is
not.** This lines up exactly with the long-open, previously unexplained
[[lesson-primary-source-recall-gap]] — base pasuk ~43% vs halacha ~100%.

Two separate effects measured directly against production, both real:
1. **Sparse/lexical**: a plain query token (`אלוה`) cannot match a niqqud-interleaved stored token —
   different token entirely to a lexical index. Near-certain zero sparse contribution for vocalized
   text.
2. **Dense**: NOT solely a sparse problem. A pure dense-only search (sparse stripped out entirely),
   scoped to foundational works with commentary refs filtered out, still does not surface `Job.31.2`
   in the top 15 — its cosine (~0.62) sits inside a dense cluster of a few dozen Tehillim
   verses/commentaries in the same 0.58–0.62 band. Niqqud makes it worse, but even a niqqud-stripped
   re-embed of the verse only moved cosine from 0.6209 → 0.6492 against the query — real, but not by
   itself enough to separate it from the pack.

**Why this isn't tonight's fix**: closing it means re-embedding Tanakh + Mishnah (hundreds of
thousands of points) and rebuilding the index for them — the same order of work as the original
commercial-corpus build on the H100, not a `hybrid.py` patch. The quote-floor tweak discussed earlier
in this session (deepen it, filter commentary refs like the base floor does) was proposed before this
was known and **would not have fixed it** — verified by testing dense-only at depth 15, which still
misses.

**Before starting a re-embed**: decide whether niqqud is stripped only for the vectors (sparse +
dense) while the stored/displayed payload text keeps it for citation display, or stripped from the
payload text entirely with niqqud-bearing text reconstructed at render time. The former is safer and
is almost certainly the right call — display fidelity has no bearing on retrievability and should not
be touched to fix it.

---

## I. Admin "show the full chat" was built, then reverted — needs a privacy policy update first

**Built, then reverted same day (2026-08-20, commit `a9e73a2` → reverted `8498ca5`). Never deployed.**

An admin reviewing a flagged/reported message could only see that ONE message — no context for what
led up to it. Built a `GET /admin/sessions/{id}/messages` route (deliberately not owner-scoped, since
a report can be about any account) plus a "הצג את כל הצ'אט" toggle in the admin panel.

Reverted on re-reading `docs/legal/privacy-he.md` §1 ("סימון הודעות לבדיקה"), which explicitly
promises: flagging "only transfers **the message** to our manual review, via a reference to its
existing message ID — **not copying content to an additional location**." §11 purpose 6 (illegal/
harmful/defamation-risk review) covers review of the flagged content; neither section describes
extending that review to the rest of a user's conversation. Showing the whole chat is a real,
meaningful expansion of what a user was told happens when a message of theirs gets flagged —
including other, unrelated things they may have asked, on the reasonable assumption only the flagged
exchange itself would ever be looked at.

**To bring this back**: update the privacy policy FIRST (new/amended clause in §1 and/or §11,
changelog entry, version bump — the same process every other policy change in this repo already
follows), then re-apply the reverted commit (`git revert 8498ca5` undoes the revert cleanly, since
nothing has touched those files since). Do not restore the feature without the policy update landing
first — that was the whole point of reverting it before it ever reached production.

## J. Institution billing: the logic is ready, nothing is reachable yet — build the UI the moment checkout opens

Decided and implemented 2026-08-20 (see `specs/004-school-accounts/plan.md`, "Decided 2026-08-20"):
a school member's own credits (student, teacher, or the admin) are now a spendable fallback once the
school's pool or their per-member cap refuses a turn — `orgs.refuse_personal_purchase`,
`_reserve_tokens`'s org branch, and `accept_invite`'s join precondition were all updated and tested.

**None of it is reachable by a real user right now, and this is the founder's explicit note to fix
that the moment institution billing is opened for payment — build it immediately, not "at some
point":**

1. **There is no real-money "buy credits" checkout at all**, for anyone, member or not.
   `CheckoutRequest`/`billing.start_checkout` only ever sell a PLAN tier. Today's fix only ensures
   that whenever this gets built, an org member won't be wrongly blocked from it — it does not
   build the flow itself.
2. **The school admin panel (`web/app/school/page.tsx`) has no buy/upgrade button at all.** The
   backend already lets the org owner check out or renew the school's own institutional plan
   (`billing.start_checkout`, unrelated to today's change) — but there is no UI in the panel that
   calls it, so the admin currently cannot click anything to buy or upgrade the institution's plan.
3. Also still open from `004-school-accounts/plan.md`: `orgs.create_org` itself is never called from
   a real checkout/webhook path — an institution purchase does not yet create an org for anyone.

Order when this opens: (3) first — nothing else matters if a real purchase never creates the org —
then (2) so the paying admin has something to click, then (1) so members can top up themselves.
