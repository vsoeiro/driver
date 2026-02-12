# List Folder Files

Lists files and folders inside a specific folder.

## Endpoint

```
GET /api/v1/drive/{account_id}/files/{item_id}
```

## Authentication

Required (session cookie or Bearer token).

## Input

| Parameter | Type | Location | Required | Description |
|-----------|------|----------|----------|-------------|
| `account_id` | string | path | Yes | UUID of the linked account |
| `item_id` | string | path | Yes | OneDrive folder ID |

## Output

```json
{
  "items": [
    {
      "id": "XYZ789",
      "name": "Project",
      "item_type": "folder",
      "size": 0,
      "child_count": 5,
      "created_at": "2024-01-10T08:00:00Z",
      "modified_at": "2024-01-15T14:30:00Z",
      "web_url": "https://onedrive.live.com/..."
    }
  ],
  "folder_path": "ABC123",
  "next_link": null
}
```

## Microsoft Graph API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/me/drive/items/{item_id}/children` | GET | List items in folder |

## Permissions Required

- `Files.Read` - Read user files
- `Files.Read.All` - Read all accessible files

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 403 | Account belongs to another user |
| 404 | Account or folder not found |
