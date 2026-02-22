# Search Files

Searches for files and folders in Google Drive by name.

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
      "web_url": "https://drive.google.com/..."
    }
  ],
  "folder_path": "search:report",
  "next_link": null
}
```

## Google Drive API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/files` | GET | Search items with `q=name contains '{query}' and trashed=false` |

### Query Used

- `q=name contains '{query}' and trashed=false`
- `fields=nextPageToken,files(id,name,mimeType,size,quotaBytesUsed,createdTime,modifiedTime,webViewLink,webContentLink,parents)`
- `pageSize=100`
- `supportsAllDrives=true`
- `includeItemsFromAllDrives=true`

## Permissions Required

- `https://www.googleapis.com/auth/drive` - Full read/write access to user Drive files

## Search Behavior

- Searches by file and folder name
- Case insensitive on Drive backend behavior
- Supports partial matches (`contains`)
- Excludes trashed items

## Example

```bash
curl "http://localhost:8000/api/v1/drive/{account_id}/search?q=report"
```

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 422 | Query parameter missing or empty |
