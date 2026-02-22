# List Linked Accounts

Returns all active linked accounts.

## Endpoint

```
GET /api/v1/accounts
```

## Authentication

Required (session cookie or Bearer token).

## Input

No parameters.

## Output

```json
{
  "accounts": [
    {
      "id": "uuid",
      "email": "user@example.com",
      "display_name": "John Doe",
      "provider": "google",
      "is_active": true,
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 1
}
```

| Field | Type | Description |
|-------|------|-------------|
| `accounts` | array | List of linked accounts |
| `total` | integer | Total number of accounts |

### Account Object

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Internal account UUID |
| `email` | string | Account email |
| `display_name` | string | Display name |
| `provider` | string | Provider name (`microsoft` or `google`) |
| `is_active` | boolean | Whether account is active |
| `created_at` | datetime | When account was linked |

## Provider API

None called (reads from local database).

## Permissions Required

None (local data only).

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
