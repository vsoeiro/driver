# Get Shared Files

Returns files shared with the current user.

## Endpoint

```
GET /api/v1/drive/{account_id}/shared
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
      "id": "XYZ789",
      "name": "shared-document.docx",
      "item_type": "file",
      "size": 51200,
      "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "modified_at": "2024-01-14T10:00:00Z",
      "web_url": "https://onedrive.live.com/..."
    }
  ],
  "folder_path": "shared",
  "next_link": null
}
```

## Microsoft Graph API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/me/drive/sharedWithMe` | GET | List items shared with me |

## Permissions Required

- `Files.Read` - Read user files
- `Files.Read.All` - Read all accessible files

## Notes

- Includes files and folders shared by other users
- Shows items from other people's OneDrive/SharePoint
- Does not include items you shared with others

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 404 | Account not found |
