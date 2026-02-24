# List Folder Files

Lists files and folders inside a specific Dropbox folder.

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
| `item_id` | string | path | Yes | Dropbox folder ID |

## Output

```json
{
  "items": [
    {
      "id": "XYZ789",
      "name": "Project",
      "item_type": "folder",
      "size": 0,
      "created_at": "2024-01-10T08:00:00Z",
      "modified_at": "2024-01-15T14:30:00Z",
      "web_url": "https://www.dropbox.com/home/..."
    }
  ],
  "folder_path": "ABC123",
  "next_link": null
}
```

## Dropbox API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/files` | GET | List folder children with `q='{item_id}' in parents and trashed=false` |

### Query Used

- `q='{item_id}' in parents and trashed=false`
- `fields=nextPageToken,files(id,name,mimeType,size,quotaBytesUsed,createdTime,modifiedTime,webViewLink,webContentLink,parents)`
- `pageSize=200`
- `supportsAllDrives=true`
- `includeItemsFromAllDrives=true`

## Permissions Required

- `account_info.read + files.metadata.read + files.content.read + files.content.write` - Full read/write access to user Drive files

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 403 | Account belongs to another user |
| 404 | Account or folder not found |
