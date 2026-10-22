# Schedule API

Follows the team's database diagram: each `Schedule` row is one work block for one employee on one day.

All endpoints are under `/api/schedules/`, require `Authorization: Bearer <access token>`
(from `POST /api/login/`), and return JSON. Missing/invalid token → `401`.

## Status codes and errors

| Code | Meaning |
|------|---------|
| 200 | OK (read, update) |
| 201 | Created |
| 204 | Deleted (no body) |
| 400 | Validation failed. Body is `{ "<field>": ["message", ...] }`; cross-field errors appear under `non_field_errors` |
| 401 | Missing, expired or invalid token |
| 404 | Schedule does not exist |

Example 400: `{"end_time": ["end_time must be after start_time (overnight shifts are not supported)."]}`

## Endpoints

| Method | URL | Notes |
|--------|-----|-------|
| GET | `/api/schedules/` | List, ordered by `shift_date`, `start_time`. Optional filters below |
| POST | `/api/schedules/` | Create |
| GET | `/api/schedules/{id}/` | Read one |
| PUT | `/api/schedules/{id}/` | Replace (all required fields) |
| PATCH | `/api/schedules/{id}/` | Partial update |
| DELETE | `/api/schedules/{id}/` | Delete |

### List filters (all optional, combine freely)

| Param | Example | Meaning |
|-------|---------|---------|
| `employee` | `?employee=4` | Employee Profile id |
| `department` | `?department=2` | Employees in that department |
| `status` | `?status=scheduled` | `scheduled`, `completed` or `cancelled` |
| `shift_date` | `?shift_date=2026-10-19` | Exactly that day |
| `date_from`, `date_to` | `?date_from=2026-10-19&date_to=2026-10-25` | Inclusive range. Use this for a weekly view |

A malformed filter value returns `400` naming the parameter.

## Request body (POST / PUT / PATCH)

```json
{
  "task_name": "Register",
  "employee": 4,
  "shift_date": "2026-10-19",
  "start_time": "09:00",
  "end_time": "17:00",
  "status": "scheduled",
  "notes": "Opening"
}
```

| Field | Required | Rules |
|-------|----------|-------|
| `task_name` | yes | Non-blank text, max 255 |
| `employee` | yes | Id of an existing Employee Profile |
| `shift_date` | yes | `YYYY-MM-DD` |
| `start_time`, `end_time` | yes | `HH:MM` or `HH:MM:SS`. `end_time` must be after `start_time` (no overnight shifts) |
| `status` | no | `scheduled` (default), `completed`, `cancelled` |
| `notes` | no | Free text |

`id`, `employee_name`, `created_at` and `modified_at` are read-only and ignored if sent.

**Double-booking:** a schedule that overlaps another non-cancelled one for the same employee on the same day
is rejected with `400`. Touching times (one ends at 17:00, the next starts at 17:00) are allowed.
Cancelled rows never block anything.

## Response

```json
{
  "id": 12, "task_name": "Register", "employee": 4, "employee_name": "Eve Worker",
  "shift_date": "2026-10-19", "start_time": "09:00:00", "end_time": "17:00:00",
  "status": "scheduled", "notes": "Opening",
  "created_at": "2026-10-19T22:40:00Z", "modified_at": "2026-10-19T22:40:00Z"
}
```

The list endpoint returns a plain JSON array of these objects.

## Supporting tables added with it

`Company`, `Department` and `EmployeeProfile` (from the diagram) exist so `employee` has something to point at.
There are no API endpoints for them yet. Create them in the Django admin (`/admin/`).
`EmployeeProfile.role` uses `ceo` / `manager` / `employee`.

## Not included yet

- Access scoping by role or department. For now any authenticated user can access every schedule.
- Compatibility, availability, time-off and project tables from the diagram.

## Tests

```powershell
cd backend
$env:SECRET_KEY = "dev-secret-key-change-me-at-least-32-characters"; $env:DEBUG = "True"
python manage.py test
```
