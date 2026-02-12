# Search Files

Searches for files and folders in OneDrive by name or content.

## Endpoint

```
GET /api/v1/drive/{account_id}/search
```

## Authentication

Required (session cookie or Bearer token).

## Input

| Parameter | Type | Location | Required | Description |
|-----------|------|----------|----------|-------------|
| `account_id` | string | path | Yes | UUID of the linked account |
| `q` | string | query | Yes | Search query (min 1 char) |

## Output

```json
{
  "items": [
    {
      "id": "ABC123",
      "name": "quarterly-report.xlsx",
      "item_type": "file",
      "size": 51200,
      "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "created_at": "2024-01-10T08:00:00Z",
      "modified_at": "2024-01-15T14:30:00Z",
      "web_url": "https://onedrive.live.com/..."
    }
  ],
  "folder_path": "search:report",
  "next_link": null
}
```

## Microsoft Graph API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/me/drive/root/search(q='{query}')` | GET | Search for items |

## Permissions Required

- `Files.Read` - Read user files
- `Files.Read.All` - Read all accessible files

## Search Behavior

- Searches file names and content
- Case insensitive
- Supports partial matches
- Results ordered by relevance

## Example

```bash
curl "http://localhost:8000/api/v1/drive/{account_id}/search?q=report"
```

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 422 | Query parameter missing or empty |
