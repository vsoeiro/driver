# List Linked Accounts

Returns all Microsoft accounts linked to the current user.

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
      "microsoft_id": "abc123",
      "email": "user@outlook.com",
      "display_name": "John Doe",
      "linked_at": "2024-01-15T10:30:00Z",
      "is_primary": true
    }
  ],
  "count": 1
}
```

| Field | Type | Description |
|-------|------|-------------|
| `accounts` | array | List of linked accounts |
| `count` | integer | Total number of accounts |

### Account Object

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Internal account UUID |
| `microsoft_id` | string | Microsoft account ID |
| `email` | string | Microsoft email |
| `display_name` | string | Display name |
| `linked_at` | datetime | When account was linked |
| `is_primary` | boolean | If this is the primary account |

## Microsoft Graph API

None called (reads from local database).

## Permissions Required

None (local data only).

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
