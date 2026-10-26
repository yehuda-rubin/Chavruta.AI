# API Contract: School-Track Minors Support

The backend is FastAPI (`app/api.py`). Every new prefix MUST be listed in **both** `docker/nginx.conf` and
`web/next.config.mjs`. `tests/unit/test_api_proxy_coverage.py` enforces this from `web/lib/api.ts`.
Errors use the existing `{"error": code, "message": text}` shape.

## Account and age

| Method | Path | Who | Body | Result |
|---|---|---|---|---|
| POST | /account/age | self, once | `{birth_year, birth_month}` | 200 `{is_minor, adult_from}` · 409 `age_already_set` · 422 `under_minimum_age` |
| POST | /account/adult-terms | self, when `adult_terms_required` | `{terms_version}` | 200 |
| GET | /me | self | — | adds `is_minor`, `age_required`, `adult_terms_required`, `school_linked` |

`require_auth` adds three new 403 codes:
- `age_required`: a new account without an age record that has no legacy `age_confirmed_18`.
- `adult_terms_required`: returned on message-sending routes only.
- `minor_no_purchase`: returned on billing, coupon and referral routes.

## School linking

| Method | Path | Who | Body | Result |
|---|---|---|---|---|
| POST | /orgs/join-requests | org admin | `{owner_id}` | 201 `{id}`. 404 if the owner is unknown, which reveals nothing. |
| GET | /account/join-requests | self | — | pending requests (org name only) |
| POST | /account/join-requests/{id} | self | `{decision: "approve" \| "decline"}` | 200 |
| POST | /orgs/invite | (existing, unchanged) | | join link with `max_uses` and expiry |
| POST | /orgs/join | (existing) | | for a minor joiner, sets `org_members.is_minor = 1` |

The school admin never receives a student's age, birth data, or `is_minor` value beyond a "minor" badge
needed for alerts.

## Parent

| Method | Path | Who | Body | Result |
|---|---|---|---|---|
| POST | /parent/links | adult self | `{child_owner_id}` | 201. 404 if not found or not a minor. |
| POST | /account/parent-links/{parent_id} | child | `{decision}` | 200 |
| DELETE | /parent/links/{child_id} | parent or child | — | 204, revokes the link |
| PUT | /parent/children/{child_id}/age | active parent | `{birth_year, birth_month}` | 200. The change is logged. |
| GET / PUT | /parent/children/{child_id}/content | active parent | `{disabled: [{kind, value}]}` | 200 |

## Content settings (school)

| Method | Path | Who | Body | Result |
|---|---|---|---|---|
| GET | /orgs/content | org admin | — | category tree + books, each `{id, label_he, label_en, enabled}` |
| PUT | /orgs/content | org admin | `{disabled: [{kind, value}]}` | 200. Logged to `org_access_log`. |

## Safety contacts and alerts

| Method | Path | Who | Body | Result |
|---|---|---|---|---|
| PUT | /orgs/safety-contacts | org admin | `{owner_ids: [...]}` | 200 |
| GET | /orgs/alerts | safety contact or org admin | — | `[{id, student_label, category, immediate_danger, created_at, acknowledged}]`. No text. |
| POST | /orgs/alerts/{id}/ack | safety contact | — | 200 |
| GET | /admin/crisis-alerts | operator | — | same shape across all orgs plus unlinked minors |

## Crisis reply (inside the existing query and stream responses)

When screening fires for a minor, the normal answer payload is replaced by:

```json
{"kind": "crisis", "category": "self_harm|suicide|abuse|danger", "immediate_danger": true,
 "message_he": "...", "message_en": "...",
 "contacts": [{"id": "eran", "label_he": "ער\"ן", "tel": "1201", "whatsapp": "...", "chat_url": "..."},
              {"id": "sahar", "label_he": "סה\"ר", "whatsapp": "...", "chat_url": "..."},
              {"id": "police", "label_he": "משטרה", "tel": "100", "only_if_danger": true}]}
```

- The contact list lives in one versioned config file and is verified before release (FR-012).
- The message texts are fixed and written by a human, never generated.

## Admin views (changed shape for minor rows)

`/admin/flagged-messages` and `/admin/feedback` return the following for rows written by a minor:
`{id, category, snippet_redacted, created_at, minor: true}`. They omit `owner_id`, `session_id` and the full
text.
