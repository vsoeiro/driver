# Get File Metadata

Gets detailed metadata for a specific file or folder in Dropbox.

## Endpoint

```
GET /api/v1/drive/{account_id}/file/{item_id}
```

## Authentication

Required (session cookie or Bearer token).

## Input

| Parameter | Type | Location | Required | Description |
|-----------|------|----------|----------|-------------|
| `account_id` | string | path | Yes | UUID of the linked account |
| `item_id` | string | path | Yes | Dropbox item ID |

## Output

```json
{
  "id": "ABC123",
  "name": "document.docx",
  "item_type": "file",
  "size": 25600,
  "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "created_at": "2024-01-10T08:00:00Z",
  "modified_at": "2024-01-15T14:30:00Z",
  "web_url": "https://www.dropbox.com/home/...",
  "download_url": "https://..."
}
```

## Dropbox API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/files/{item_id}` | GET | Get item metadata |

### Query Used

- `fields=id,name,mimeType,size,quotaBytesUsed,createdTime,modifiedTime,webViewLink,webContentLink,parents`
- `supportsAllDrives=true`

## Permissions Required

- `account_info.read + files.metadata.read + files.content.read + files.content.write` - Full read/write access to user Drive files

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 403 | Account belongs to another user |
| 404 | Account or item not found |
