# Get Download URL

Gets a direct download URL for a Google Drive file.

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
| `item_id` | string | path | Yes | Google Drive file ID |

## Output

```json
{
  "download_url": "https://..."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `download_url` | string | Direct download URL from `webContentLink` |

## Google Drive API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/files/{item_id}` | GET | Load `webContentLink` for direct download |

### Query Used

- `fields=id,name,mimeType,webContentLink`
- `supportsAllDrives=true`

## Permissions Required

- `https://www.googleapis.com/auth/drive` - Full read/write access to user Drive files

## Notes

- Native Google Docs files (`application/vnd.google-apps.*`) do not provide `webContentLink`
- When no direct link is available, the API returns an error

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 403 | Account belongs to another user |
| 404 | Account or file not found |
| 400 | Native Google Docs file (no direct download URL) |
