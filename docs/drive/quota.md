# Get Quota

Returns storage quota information for the OneDrive account.

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
| `state` | string | Quota state |

### Quota States

| State | Description |
|-------|-------------|
| `normal` | Plenty of space available |
| `nearing` | Approaching storage limit |
| `critical` | Almost out of space |
| `exceeded` | Storage limit exceeded |

## Microsoft Graph API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/me/drive` | GET | Get drive info including quota |

## Permissions Required

- `Files.Read` - Read user files

## Example Response Calculation

```
Total:     5 GB = 5,368,709,120 bytes
Used:      1 GB = 1,073,741,824 bytes
Remaining: 4 GB = 4,294,967,296 bytes
```

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 404 | Account not found |
