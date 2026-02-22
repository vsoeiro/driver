# List Root Files

Lists files and folders in the root of Google Drive.

## Endpoint

```
GET /api/v1/drive/{account_id}/files
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
  "items": [
    {
      "id": "ABC123",
      "name": "Documents",
      "item_type": "folder",
      "size": 0,
      "created_at": "2024-01-10T08:00:00Z",
      "modified_at": "2024-01-15T14:30:00Z",
      "web_url": "https://drive.google.com/..."
    },
    {
      "id": "DEF456",
      "name": "report.pdf",
      "item_type": "file",
      "size": 1048576,
      "mime_type": "application/pdf",
      "created_at": "2024-01-12T09:00:00Z",
      "modified_at": "2024-01-12T09:00:00Z",
      "web_url": "https://drive.google.com/...",
      "download_url": "https://..."
    }
  ],
  "folder_path": "/",
  "next_link": null
}
```

## Google Drive API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/files` | GET | List root items with `q='root' in parents and trashed=false` |

### Query Used

- `q='root' in parents and trashed=false`
- `fields=nextPageToken,files(id,name,mimeType,size,quotaBytesUsed,createdTime,modifiedTime,webViewLink,webContentLink,parents)`
- `pageSize=200`
- `supportsAllDrives=true`
- `includeItemsFromAllDrives=true`

## Permissions Required

- `https://www.googleapis.com/auth/drive` - Full read/write access to user Drive files

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 403 | Account belongs to another user |
| 404 | Account not found |
