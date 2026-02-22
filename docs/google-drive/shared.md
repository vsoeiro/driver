# Get Shared Files

Returns files shared with the current user in Google Drive.

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
      "web_url": "https://drive.google.com/..."
    }
  ],
  "folder_path": "shared",
  "next_link": null
}
```

## Google Drive API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/files` | GET | List items shared with me |

### Query Used

- `q=sharedWithMe = true and trashed=false`
- `fields=nextPageToken,files(id,name,mimeType,size,quotaBytesUsed,createdTime,modifiedTime,webViewLink,webContentLink,parents)`
- `pageSize=100`
- `supportsAllDrives=true`
- `includeItemsFromAllDrives=true`

## Permissions Required

- `https://www.googleapis.com/auth/drive` - Full read/write access to user Drive files

## Notes

- Includes files and folders shared by other users
- Does not include items you shared with others

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 404 | Account not found |
