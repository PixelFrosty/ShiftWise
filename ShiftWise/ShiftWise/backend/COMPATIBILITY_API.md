# Compatibility API

Follows the "Compatibility Scoring" table in the team diagram: how well two employees work together.

All endpoints are under `/api/compatibility/`, require `Authorization: Bearer <access token>`, and return JSON.
Missing/invalid token → `401`. Status codes and error body format are the same as in `SCHEDULE_API.md`.

## Endpoints

| Method | URL | Notes |
|--------|-----|-------|
| GET | `/api/compatibility/` | List. Optional `?employee=<id>` returns every rating involving that employee (either side) |
| POST | `/api/compatibility/` | Create |
| GET | `/api/compatibility/{id}/` | Read one |
| PUT / PATCH | `/api/compatibility/{id}/` | Update. In practice you change `score` |
| DELETE | `/api/compatibility/{id}/` | Delete |

## Request body

```json
{ "employee_a": 3, "employee_b": 7, "score": "8.5" }
```

| Field | Required | Rules |
|-------|----------|-------|
| `employee_a`, `employee_b` | yes | Ids of two different Employee Profiles in the same company |
| `score` | yes | Number from 0 to 10, up to 2 decimal places |

`id`, `employee_a_name`, `employee_b_name` and `rated_by` are read-only. `rated_by` is set to the logged-in
user on create and update.

## Rules

- **One rating per pair.** The pair is unordered: `(3, 7)` and `(7, 3)` are the same pair. The server always
  stores the lower id as `employee_a`, so the response may swap the two ids you sent.
- Rating a pair that already has a rating returns `400` with the id of the existing rating. Update it instead.
- An employee cannot be rated against themselves (`400`).
- The pair on an existing rating cannot be changed (`400`). Delete it and create a new one.
- A pair with no rating means "not rated yet". Consumers (the scheduler) should treat that as neutral.

## Response

```json
{
  "id": 1, "employee_a": 3, "employee_a_name": "Ann Smith",
  "employee_b": 7, "employee_b_name": "Bob Jones",
  "score": "8.50", "rated_by": 2
}
```

The list endpoint returns a plain JSON array of these objects.
