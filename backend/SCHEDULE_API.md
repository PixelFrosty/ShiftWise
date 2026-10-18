# Schedule & Shift API

All endpoints are under `/api/`, require `Authorization: Bearer <access token>` (from `POST /api/login/`),
and return JSON. Missing/invalid token → `401`.

## Status codes and errors

| Code | Meaning |
|------|---------|
| 200 | OK (read, update) |
| 201 | Created |
| 204 | Deleted (no body) |
| 400 | Validation failed. Body is `{ "<field>": ["message", ...] }`; cross-field errors appear under `non_field_errors` |
| 401 | Missing, expired or invalid token |
| 404 | Schedule/shift does not exist (or shift is not under that schedule) |

Example 400: `{"end": ["end must be after start."]}`

## Schedules

A schedule covers one week. `week_start` must be a **Monday**.

| Method | URL | Notes |
|--------|-----|-------|
| GET | `/api/schedules/` | List. Optional filters: `?week_start=YYYY-MM-DD`, `?status=draft\|published` |
| POST | `/api/schedules/` | Create |
| GET | `/api/schedules/{id}/` | Detail, includes nested `shifts` |
| PUT / PATCH | `/api/schedules/{id}/` | Full / partial update |
| DELETE | `/api/schedules/{id}/` | Deletes the schedule and all its shifts |

Request body (POST/PUT):

```json
{ "name": "Front counter", "week_start": "2026-10-19", "status": "draft" }
```

`name` and `week_start` are required. `status` is optional (`draft` default, or `published`).
`created_by` is set from the logged-in user and ignored if sent.
`week_start` cannot be changed while the schedule has shifts.

Response (list item; detail adds `shifts`):

```json
{
  "id": 1, "name": "Front counter", "week_start": "2026-10-19", "status": "draft",
  "created_by": 3, "shift_count": 2,
  "date_created": "2026-10-18T22:40:00Z", "date_modified": "2026-10-18T22:40:00Z",
  "shifts": [ { "id": 7, "schedule": 1, "start": "2026-10-19T14:00:00Z",
                "end": "2026-10-19T22:00:00Z", "headcount_needed": 2, "notes": "Opening" } ]
}
```

## Shifts (nested under a schedule)

| Method | URL |
|--------|-----|
| GET / POST | `/api/schedules/{schedule_id}/shifts/` |
| GET / PUT / PATCH / DELETE | `/api/schedules/{schedule_id}/shifts/{id}/` |

Request body:

```json
{ "start": "2026-10-19T14:00:00Z", "end": "2026-10-19T22:00:00Z", "headcount_needed": 2, "notes": "Opening" }
```

- `start`, `end` required, ISO 8601 datetimes (UTC `Z` recommended).
- `end` must be after `start`; both must fall inside the schedule's week
  (Monday 00:00 to the following Monday 00:00 in the server timezone).
- `headcount_needed` optional, integer ≥ 1, default 1. `notes` optional, max 255 chars.
- `schedule` in responses is the parent schedule id (read-only).

## Not included yet

- Assigning employees to shifts (`ShiftAssignment`) and a Department link on schedules.
- Per-role / per-owner access scoping (Phase 4). For now any authenticated user can access every schedule.

## Tests

```bash
cd backend && SECRET_KEY=dev DEBUG=True python manage.py test
# or: podman-compose exec backend python manage.py test
```