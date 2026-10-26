# Data Model: School-Track Minors Support

All tables are added in one `chavruta.db` migration (`SCHEMA_VERSION` 34 → 35, in `app/db.py::_migrate`).
No real user text appears in any example.

## age_records (new)

| Column | Type | Rules |
|---|---|---|
| owner_id | TEXT PK | Supabase `sub` |
| birth_year | INTEGER NOT NULL | 1900 ≤ y ≤ current year |
| birth_month | INTEGER NOT NULL | 1–12 |
| adult_from | TEXT NOT NULL | ISO date. The first day of the month after the 18th birthday month. This is conservative: the account becomes adult no earlier than the true birthday. |
| adult_terms_accepted_at | TEXT NULL | Set by `POST /account/adult-terms` |
| created_at, updated_at | TEXT | |

- **Derived**: `is_minor = today < adult_from`.
- **Validation**: refuse if age < 12 at creation (FR-001).
- **Write rule**: the record can be created once by the owner. After that, only a linked parent
  (`parent_links.status='active'`) or the operator can change it. Every change appends to `age_record_log`.

## age_record_log (new)

Columns: `id`, `owner_id`, `actor`, `actor_kind` (`self` | `parent` | `operator`), `old_birth_year`,
`old_birth_month`, `new_birth_year`, `new_birth_month`, `at`. The log is never purged while the account exists,
and it is deleted with the account.

## messages, saved_lessons, saved_source_sheets (extended)

- Each table gains `minor_until TEXT NULL`. The value is the deletion date (write time + minor retention days)
  when the author was a minor at write time, and NULL otherwise.
- **Immutable**: no code path updates it after insert.
- Index `idx_messages_minor_until` supports the retention sweep.

## org_members (extended)

- Gains `is_minor INTEGER NOT NULL DEFAULT 0`. It is set at join time from `age_records`, for display and
  alerts only.
- The source of truth for minor status is always `age_records`.

## org_join_requests (new)

| Column | Type | Rules |
|---|---|---|
| id | INTEGER PK | |
| org_id | TEXT | |
| owner_id | TEXT | the student |
| requested_by | TEXT | org admin |
| status | TEXT | `pending` → `approved` / `declined` / `expired` |
| created_at, decided_at | TEXT | expires after `INVITE_DAYS` |

When a request is approved, the same membership insert as `orgs.accept_invite` runs, and it respects the
one-org-per-account unique index and sticky removal.

## parent_links (new)

| Column | Type | Rules |
|---|---|---|
| parent_owner_id | TEXT | must be adult (age record ≥ 18 or legacy `age_confirmed_18`) |
| child_owner_id | TEXT | must be a minor at request time |
| status | TEXT | `pending` → `active` / `declined` / `revoked` |
| created_at, decided_at | TEXT | |

The primary key is (`parent_owner_id`, `child_owner_id`). A child may have up to two active parents.

## content_denylist (new)

| Column | Type | Rules |
|---|---|---|
| scope_kind | TEXT | `org` \| `parent` |
| scope_id | TEXT | org_id or parent link's child_owner_id |
| kind | TEXT | `category` \| `work` |
| value | TEXT | category path or work_id |
| set_by, set_at | TEXT | |

- Each change also writes to `org_access_log` (org scope) or `age_record_log`-style parent log.
- **Effective denylist** for a minor = union over the minor's org and active parents. Categories are expanded
  to work_ids. Adults: always empty.

## orgs (extended)

Gains `safety_contacts TEXT` (a JSON list of member owner_ids, admin- or teacher-role, who receive crisis
alerts).

## crisis_alerts (new)

| Column | Type | Rules |
|---|---|---|
| id | INTEGER PK | |
| owner_id | TEXT | student |
| org_id | TEXT NULL | NULL for an unlinked minor, in which case only the operator receives the alert |
| category | TEXT | `self_harm` \| `suicide` \| `abuse` \| `danger` |
| immediate_danger | INTEGER | |
| detector | TEXT | `phrase` \| `classifier` |
| created_at | TEXT | |
| delivered_at | TEXT NULL | |
| acknowledged_by, acknowledged_at | TEXT NULL | |

**No message text, ever.** The table is purged with the account and also on the minor retention schedule.

## State transitions

- **Account**:
  - `new` → (POST /account/age, age ≥ 12) → `minor` | `adult`.
  - `minor` → (today ≥ adult_from) → `adult_pending_terms` → (POST /account/adult-terms) → `adult`.
  - `adult_pending_terms` cannot send messages.
- **Join request**: `pending` → `approved` | `declined` | `expired`.
- **Parent link**: `pending` → `active` → `revoked`.

## purge_owner

`purge_owner` (`app/db.py:2544`) MUST be extended to delete the account's rows from all new tables. Fix the
existing gap in the same change: the `referral_*` tables are not purged today.
