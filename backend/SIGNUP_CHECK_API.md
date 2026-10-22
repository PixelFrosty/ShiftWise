# Signup Check API

Endpoint to check whether an email or username is already registered before submitting the registration form.
To prevent user enumeration / privacy leaks, the endpoint never specifies which field is taken—only whether one or the other is already in use.

The endpoint is public (accessible without authentication) and is a read-only query using `GET`.

## Endpoints

| Method | URL | Notes |
|--------|-----|-------|
| `GET` | `/api/signup-check/` or `/api/signup-check` | Query params: `?email=...&username=...` |

## Status Codes and Responses

| Code | Meaning | Response Body |
|------|---------|---------------|
| `200` | Available | `{"taken": false, "message": "Email and username are available."}` |
| `409` | Taken | `{"taken": true, "message": "Email or username has already been taken."}` |
| `400` | Bad Request | `{"detail": "Both 'email' and 'username' must be provided."}` |
| `405` | Method Not Allowed | Returned if non-GET methods (e.g. POST) are called |

## Request Parameters

Both `email` and `username` must be provided in the query string.

| Parameter | Type | Required | Notes |
|-----------|------|----------|-------|
| `email` | string | **Yes** | Email address to check (case-insensitive) |
| `username` | string | **Yes** | Username to check (case-insensitive) |

## Examples

### 1. Check with GET (Available - 200 OK)

```http
GET /api/signup-check/?username=johndoe&email=john%40example.com HTTP/1.1
```

**Response (200 OK):**
```json
{
  "taken": false,
  "message": "Email and username are available."
}
```

### 2. Check with GET (Taken - 409 Conflict)

```http
GET /api/signup-check/?username=johndoe&email=existing%40example.com HTTP/1.1
```

**Response (409 Conflict):**
```json
{
  "taken": true,
  "message": "Email or username has already been taken."
}
```

### 3. Missing Inputs (400 Bad Request)

If either `email` or `username` is omitted or empty:

```http
GET /api/signup-check/?username=johndoe HTTP/1.1
```

**Response (400 Bad Request):**
```json
{
  "detail": "Both 'email' and 'username' must be provided."
}
```

## Running Tests

```bash
USE_SQLITE=1 python backend/manage.py test api.tests.SignupCheckApiTests
```
