# Availability, Time-off and Project APIs

Follow the "Availability Slot", "Time-off Requests" and "Project" tables in the team diagram.
All endpoints require `Authorization: Bearer <access token>` and return JSON (`401` without a token).
Status codes and the error body format are the same as in `SCHEDULE_API.md`. Each resource has the usual five
methods: `GET` list, `POST` create, `GET/PUT/PATCH/DELETE` on the detail URL. List endpoints return a plain
JSON array. A malformed filter value returns `400` naming the parameter.

---

## Availability: `/api/availability/` and `/api/availability/{id}/`

A recurring weekly slot: an employee is available on a day of the week between two times.

```json
{ "employee": 4, "day_of_week": 0, "start_time": "09:00", "end_time": "17:00" }
```

| Field | Required | Rules |
|-------|----------|-------|
| `employee` | yes | Employee Profile id |
| `day_of_week` | yes | Whole number 0 (Monday) to 6 (Sunday) |
| `start_time`, `end_time` | yes | `HH:MM` or `HH:MM:SS`. `end_time` must be after `start_time` (no overnight slots) |

Read-only in responses: `id`, `employee_name`, `day_name` (e.g. "Monday").
An employee can have several slots on one day (a split day) as long as they do not overlap (`400`).
Touching slots (17:00 end, 17:00 start) are fine.

Filters: `?employee=<id>` `?department=<id>` `?day_of_week=0-6`

---

## Time-off requests: `/api/time-off/` and `/api/time-off/{id}/`

```json
{ "employee": 4, "start_date": "2026-11-02", "end_date": "2026-11-04", "reason": "Family trip" }
```

| Field | Required | Rules |
|-------|----------|-------|
| `employee` | yes | Employee Profile id |
| `start_date`, `end_date` | yes | `YYYY-MM-DD`. `end_date` may equal `start_date` (one day) but not be earlier |
| `reason` | no | Free text |
| `status` | no | `pending`, `approved` or `denied`. New requests must be `pending` (the default) |

Read-only: `id`, `employee_name`, `requested_at`.

- **Approve or deny** with `PATCH /api/time-off/{id}/` and `{"status": "approved"}` or `{"status": "denied"}`.
- A request that overlaps another non-denied request for the same employee is rejected (`400`). Denied
  requests never block anything. Moving a denied request back to pending or approved re-checks for overlap.
- The diagram's table has no "decided by / decided at" columns, so decisions are not logged yet.

Filters: `?employee=<id>` `?department=<id>` `?status=pending|approved|denied`
`?date_from=YYYY-MM-DD` `?date_to=YYYY-MM-DD` (requests that overlap that window, ends included)

---

## Projects: `/api/projects/` and `/api/projects/{id}/`

```json
{ "company": 1, "department": 2, "name": "Store remodel", "description": "Q4 refresh", "priority": "high", "is_active": true }
```

| Field | Required | Rules |
|-------|----------|-------|
| `company` | yes | Company id |
| `department` | no | Department id (or `null`). Must belong to the same company |
| `name` | yes | Non-blank, max 255 |
| `description` | no | Free text |
| `priority` | no | `low`, `medium` (default) or `high` |
| `is_active` | no | `true` (default) or `false` |

Read-only: `id`, `created_at`, `modified_at`. Deleting a department keeps its projects and sets
their `department` to `null`.

Filters: `?company=<id>` `?department=<id>` `?priority=low|medium|high` `?is_active=true|false`

---

## Not included yet

- Access scoping by role or department. Any authenticated user can read and change everything, including
  approving their own time off.
- Time-off and availability are not yet checked when creating schedule rows.
