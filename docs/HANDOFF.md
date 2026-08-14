# Handoff — where things stand

**As of 2026-08-14 06:30 UTC.** Update this file in place rather than making a dated copy of it;
the point is that there is one place to read, not an archive to search.

---

## 1. Production right now

| | |
|---|---|
| Live at | `chavrutaai.org` — VM `chavruta@89.169.99.221`, repo at `~/chavruta` |
| Branch deployed | `001-chavruta-redesign` @ `a3e0af7`; `main` merged at `f513fdd` |
| Schema | `user_version` **30** |
| Collection | `chavruta_commercial`, 2.4M points, on-disk (`CHAVRUTA_MEM_TIER=ssd`) |
| Generation | Nebius, `Qwen/Qwen3-235B-A22B-Instruct-2507` |
| Data | 136 chats · 449 messages · 3 accounts · 1 org |
| Last backup | `/app-data/backup-20260814-045441-pre-v30.db` (5.4 MB, `integrity: ok`, v29) |

Background sweepers, both started at API boot and running hourly:

- **account sweeper** — due deletions (30-day grace) + chat retention (90 days)
- **billing downgrade sweeper** — ends paid access once a cancelled period lapses

They log **only when they act**. A silent hour means nothing was due, not that nothing ran. Note
also that the loop **sleeps before its first run** (`app/accounts.py::start_sweeper`), so a process
restarted more often than the interval would never sweep at all. Restarts are rare here, so this is
a note rather than a bug — but it stops being true if anything ever puts the API on a short restart
cycle.

---

## 2. Deploying — the parts that are not in the runbook

The procedure itself (backup → pull → build → up → verify → merge) works. These are the things that
have actually gone wrong.

**The 15-minute rule needs the right signal.** Deploy only if the last 15 minutes are empty — but a
`usage_events` row is written when a generation **completes**, so "0 requests" does not mean idle. A
**user message with no assistant reply after it** means a turn is running right now. On 2026-08-14 a
user message was 18 seconds old at check time and the answer took **282 seconds**; a restart on the
"0 requests" reading would have killed it four minutes in. `scripts/activity.py` prints both, and the
message list is the one to read.

**Re-check immediately before `up -d`, not once at the start.** Backup and build take minutes, and
someone can arrive in between — which is exactly what happened. `pull` and `build` do not touch the
running containers, so do those first and put the final activity check right before the restart.

**`.env` alone does not reach the container.** The `api` service declares an explicit `environment:`
block, so `.env` only fills `${...}` placeholders. A variable with no placeholder is never passed and
nothing warns. `CHAVRUTA_COST_PER_M_TOKENS` sat in `.env` for a day doing nothing this way. Adding a
new setting means adding it in **both** places.

**`nginx.conf` changes need `--force-recreate web`.** A single-file bind mount on a running container
keeps pointing at the old inode after `git pull` replaces the file. Documented at the `web` service
in `docker-compose.yml`; it has bitten before.

**A new API route needs three files, not one.** `docker/nginx.conf` and `web/next.config.mjs` must
both list the prefix or the route is dead **in production only**. `tests/unit/test_api_proxy_coverage.py`
derives the list from `web/lib/api.ts` and fails if either misses one — it was written after `/orgs`,
`/messages` and `/byok` were all live and unreachable.

**`main` is checked out in a worktree** at `C:/Users/rubin/Documents/chavruta-main-wt`, so
`git checkout main` in the primary tree fails. Merge there. And it is a **merge, not a fast-forward** —
`main` carries Pages-workflow commits that are not on the feature branch.

**`/tmp` inside the container does not survive `up -d`.** The activity probe used to live only there
and the deploy deleted it, leaving the next deploy with no gate to check. It is `scripts/activity.py`
now; copy it in with `docker compose cp scripts/activity.py api:/tmp/activity.py`.

---

## 3. Things that are true and easy to get wrong

Most of this is in `CLAUDE.md` and `docs/CORPUS.md §7`; repeated here only where it has caused a real
bug more than once.

- **Ref spellings.** The commercial corpus stores underscore-dot refs (`Bava_Metzia.3.1`), the router
  emits dotted ones. Anchoring must emit **both** via `corpus/refs.py::with_ref_variants` or the base
  pasuk silently never anchors. This was a ~50% → ~83% retrieval@8 swing.
- **`commentator_id` and `anchor_ref` are empty on all 2.4M points** and are derived at *read* time.
  Do not restore a payload filter on them and do not write a backfill — one was measured at ~5
  points/sec, i.e. days, to store what a string split already yields.
- **Quota compares an accumulated counter against the *current* limit**, so lowering a limit applies
  retroactively. Anything that drops an allowance has to consider the counter (see
  `devhelpers._clear_period_usage`, and read its two rules before calling it from anywhere new).
- **Normalized tokens = `prompt + 3 × completion`**, which matches Nebius's own 3:1 input:output
  price ratio — so a normalized token *is* the cost unit and `× $0.20/M` is the cost.
- **`concurrent.futures` does not propagate `ContextVar`s**, which silently under-billed metering.
  Anything that fans out LLM calls across threads must wrap with `metering.run_in_context`.

---

## 4. Open threads

Fully specified remediation for the security and correctness items lives in
**[OPEN-ITEMS-PLAN.md](OPEN-ITEMS-PLAN.md)**. What follows is everything else in flight.

**Waiting on other people**

- **Kosher filters.** NetSpark, Rimon, Netfree and Etrog were all sent reclassification requests;
  NetSpark had classified the site as a search engine. No replies yet. The claim made to them — that
  the service carries no outbound links — now binds us.
- **Nebius invoice.** The 4.81M vs 6.69M token attribution is asserted, not demonstrated. Reconcile
  against the next real invoice rather than re-deriving it from our own numbers.

**Product questions that need a judgement, not a fix**

- **Lesson retrieval was cut from 48 to 32** (`_INTENT_TOP_K[Intent.LESSON]`, `pipeline.py:67`) to
  match what שו"ת receives. Nobody has yet checked what that did to lesson quality. Worth a
  side-by-side on a few real lesson requests before it is treated as settled.
- **Turn latency is high and rising with agentic rounds.** Observed 2026-08-14: qa 282s (4 rounds),
  explain 84s (8 rounds), qa 72s (6 rounds). The rounds are the agentic `===NEED_SOURCES===` loop
  working as designed, but 282 seconds is long enough that a user may well assume it has died. No
  timeouts in the logs — this is real work, not a hang.
- **The `no_source` metric is misleading.** It counts "zero citations", so a clarification turn is
  recorded as a refusal. Any quality headline drawn from it is flattering by construction.

**Unfinished from earlier sessions**

- `specs/005-dicta-library/` is untracked and unfinished. Dicta's ״דרכי צדק״ is corrupt and must not
  be ingested; check user reports on the Dicta site per book before taking any of them.
- The sugya game has **no UI** — four sugyot and a working API behind a beta gate, nothing to click.
- Per-chunk `license` payload is empty and its indexes carry the wrong names (`license_he`/`license_en`
  vs the actual `license`). Harmless while the whole collection is commercial; matters only if
  per-chunk CC-BY attribution is ever wanted.
