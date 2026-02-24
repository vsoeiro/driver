# Update Item (Rename/Move)

Updates an item's metadata, used for renaming or moving files/folders in Dropbox.

## Endpoint

```
PATCH /api/v1/drive/{account_id}/items/{item_id}
```

## Authentication

Required (session cookie or Bearer token).

## Input

| Parameter | Type | Location | Required | Description |
|-----------|------|----------|----------|-------------|
| `account_id` | string | path | Yes | UUID of the linked account |
| `item_id` | string | path | Yes | ID of the item to update |

### Request Body

```json
{
  "name": "new-name.txt",
  "parent_folder_id": "TARGET_FOLDER_ID"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | No | New name for the item |
| `parent_folder_id` | string | No | New parent folder ID (to move) |

At least one field must be provided.

## Output

Returns the updated `DriveItem` object.

```json
{
  "id": "ABC123",
  "name": "new-name.txt",
  "item_type": "file",
  "modified_at": "2024-01-20T12:00:00Z",
  "web_url": "https://www.dropbox.com/home/..."
}
```

## Dropbox API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/files/{item_id}` | GET | Read current parents before move |
| `/files/{item_id}` | PATCH | Rename and/or move item |

### Query Used

- For parent lookup: `fields=parents&supportsAllDrives=true`
- For update: `fields=id,name,mimeType,size,quotaBytesUsed,createdTime,modifiedTime,webViewLink,webContentLink,parents&supportsAllDrives=true`
- For move: adds `addParents={parent_id}` and `removeParents={current_parents}`

## Permissions Required

- `account_info.read + files.metadata.read + files.content.read + files.content.write` - Full read/write access to user Drive files

## Notes

- To rename: send only `name`
- To move: send only `parent_folder_id`
- To move and rename: send both

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 400 | Invalid name or missing fields |
| 404 | Item or target folder not found |
