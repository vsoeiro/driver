# Get Download URL

Gets a temporary direct download URL for a file.

## Endpoint

```
GET /api/v1/drive/{account_id}/download/{item_id}
```

## Authentication

Required (session cookie or Bearer token).

## Input

| Parameter | Type | Location | Required | Description |
|-----------|------|----------|----------|-------------|
| `account_id` | string | path | Yes | UUID of the linked account |
| `item_id` | string | path | Yes | OneDrive file ID |

## Output

```json
{
  "download_url": "https://..."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `download_url` | string | Temporary direct download URL (expires in ~1 hour) |

## Microsoft Graph API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/me/drive/items/{item_id}` | GET | Get item with download URL |

Returns `@microsoft.graph.downloadUrl` from the response.

## Permissions Required

- `Files.Read` - Read user files
- `Files.Read.All` - Read all accessible files

## Notes

- URL is temporary and expires after approximately 1 hour
- URL can be used directly without authentication
- Only works for files, not folders

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 403 | Account belongs to another user |
| 404 | Account or file not found |
| 400 | Item is not a file |
