# Get Recent Files

Returns recently accessed files from OneDrive.

## Endpoint

```
GET /api/v1/drive/{account_id}/recent
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
      "name": "presentation.pptx",
      "item_type": "file",
      "size": 2097152,
      "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
      "modified_at": "2024-01-15T14:30:00Z",
      "web_url": "https://onedrive.live.com/..."
    }
  ],
  "folder_path": "recent",
  "next_link": null
}
```

## Microsoft Graph API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/me/drive/recent` | GET | List recently accessed items |

## Permissions Required

- `Files.Read` - Read user files
- `Files.Read.All` - Read all accessible files

## Notes

- Returns files accessed recently by the user
- Ordered by last access time (most recent first)
- Includes files from all folders

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 404 | Account not found |
