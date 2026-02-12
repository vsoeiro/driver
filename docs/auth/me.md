# Get Current User

Returns information about the currently authenticated user.

## Endpoint

```
GET /api/v1/auth/me
```

## Authentication

Required (session cookie or Bearer token).

## Input

No parameters.

## Output

```json
{
  "id": "uuid",
  "email": "user@example.com",
  "display_name": "John Doe",
  "linked_accounts_count": 2
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Internal user UUID |
| `email` | string | Primary email address |
| `display_name` | string | User's display name |
| `linked_accounts_count` | integer | Number of linked Microsoft accounts |

## Microsoft Graph API

None called (reads from local database).

## Permissions Required

None (user data stored locally).

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
