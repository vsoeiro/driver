# Update Item (Rename/Move)

Updates an item's metadata, used for renaming or moving files/folders.

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

*At least one field must be provided.*

## Output

Returns the updated `DriveItem` object.

```json
{
  "id": "ABC123",
  "name": "new-name.txt",
  "item_type": "file",
  "modified_at": "2024-01-20T12:00:00Z",
  "web_url": "https://onedrive.live.com/..."
}
```

## Microsoft Graph API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/me/drive/items/{item_id}` | PATCH | Update item metadata |

## Permissions Required

- `Files.ReadWrite` - Read and write user files
- `Files.ReadWrite.All` - Read and write all accessible files

## Notes

- To **rename**: provide only `name`
- To **move**: provide only `parent_folder_id`
- To **move and rename**: provide both

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 400 | Invalid name or missing fields |
| 404 | Item or target folder not found |
