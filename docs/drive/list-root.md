# List Root Files

Lists files and folders in the root of OneDrive.

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
      "child_count": 15,
      "created_at": "2024-01-10T08:00:00Z",
      "modified_at": "2024-01-15T14:30:00Z",
      "web_url": "https://onedrive.live.com/..."
    },
    {
      "id": "DEF456",
      "name": "report.pdf",
      "item_type": "file",
      "size": 1048576,
      "mime_type": "application/pdf",
      "created_at": "2024-01-12T09:00:00Z",
      "modified_at": "2024-01-12T09:00:00Z",
      "web_url": "https://onedrive.live.com/...",
      "download_url": "https://..."
    }
  ],
  "folder_path": "/",
  "next_link": null
}
```

## Microsoft Graph API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/me/drive/root/children` | GET | List items in root folder |

## Permissions Required

- `Files.Read` - Read user files
- `Files.Read.All` - Read all accessible files

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 403 | Account belongs to another user |
| 404 | Account not found |
