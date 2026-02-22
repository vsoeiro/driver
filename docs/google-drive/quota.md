# Get Quota

Returns storage quota information for the Google Drive account.

## Endpoint

```
GET /api/v1/drive/{account_id}/quota
```

## Authentication

Required (session cookie or Bearer token).

## Input

| Parameter | Type | Location | Required | Description |
|-----------|------|----------|----------|-------------|
| `account_id` | string | path | Yes | UUID of the linked account |

## Output

```json
{
  "total": 5368709120,
  "used": 1073741824,
  "remaining": 4294967296,
  "state": "normal"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `total` | integer | Total storage in bytes |
| `used` | integer | Used storage in bytes |
| `remaining` | integer | Available storage in bytes |
| `state` | string | Quota state (`normal` in current implementation) |

## Google Drive API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/about` | GET | Get storage quota details |

### Query Used

- `fields=storageQuota`

## Permissions Required

- `https://www.googleapis.com/auth/drive` - Full read/write access to user Drive files

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 404 | Account not found |
