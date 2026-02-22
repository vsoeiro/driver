# Get Recent Files

Returns recently accessed files from Google Drive.

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
      "web_url": "https://drive.google.com/..."
    }
  ],
  "folder_path": "recent",
  "next_link": null
}
```

## Google Drive API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/files` | GET | List recent items ordered by `viewedByMeTime desc` |

### Query Used

- `q=trashed=false`
- `orderBy=viewedByMeTime desc`
- `fields=nextPageToken,files(id,name,mimeType,size,quotaBytesUsed,createdTime,modifiedTime,webViewLink,webContentLink,parents)`
- `pageSize=100`
- `supportsAllDrives=true`
- `includeItemsFromAllDrives=true`

## Permissions Required

- `https://www.googleapis.com/auth/drive` - Full read/write access to user Drive files

## Notes

- Results are ordered by most recently viewed first
- Excludes trashed items

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 404 | Account not found |
