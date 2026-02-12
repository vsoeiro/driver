# Delete Item

Deletes a file or folder (moves to recycle bin).

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

## Microsoft Graph API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/me/drive/items/{item_id}` | DELETE | Delete item |

## Permissions Required

- `Files.ReadWrite` - Read and write user files
- `Files.ReadWrite.All` - Read and write all accessible files

## Notes

- Items are moved to the user's recycle bin
- They can be restored from the OneDrive recycle bin UI
- Deleting a folder deletes all its contents

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 404 | Item not found |
