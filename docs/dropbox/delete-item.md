# Delete Item

Deletes a file or folder from Dropbox.

## Endpoint

```
DELETE /api/v1/drive/{account_id}/items/{item_id}
```

## Authentication

Required (session cookie or Bearer token).

## Input

| Parameter | Type | Location | Required | Description |
|-----------|------|----------|----------|-------------|
| `account_id` | string | path | Yes | UUID of the linked account |
| `item_id` | string | path | Yes | ID of the item to delete |

## Output

HTTP 204 No Content.

## Dropbox API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/files/{item_id}` | DELETE | Delete item |

### Query Used

- `supportsAllDrives=true`

## Permissions Required

- `account_info.read + files.metadata.read + files.content.read + files.content.write` - Full read/write access to user Drive files

## Notes

- Uses Dropbox `files.delete`
- Deleting a folder removes all descendants
- Item removal is also reflected in the local item index

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 404 | Item not found |
