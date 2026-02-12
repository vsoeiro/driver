# Copy Item

Copies a file or folder to a new location.

## Endpoint

```
POST /api/v1/drive/{account_id}/items/{item_id}/copy
```

## Authentication

Required (session cookie or Bearer token).

## Input

| Parameter | Type | Location | Required | Description |
|-----------|------|----------|----------|-------------|
| `account_id` | string | path | Yes | UUID of the linked account |
| `item_id` | string | path | Yes | ID of the item to copy |

### Request Body

```json
{
  "name": "Copy of Report.docx",
  "parent_folder_id": "root"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | No | - | Name for the copy (defaults to original) |
| `parent_folder_id` | string | No | "root" | Destination folder ID |

## Output

```json
{
  "monitor_url": "https://..."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `monitor_url` | string | URL to poll for operation status |

## Microsoft Graph API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/me/drive/items/{item_id}/copy` | POST | Copy item (async operation) |

## Permissions Required

- `Files.ReadWrite` - Read and write user files
- `Files.ReadWrite.All` - Read and write all accessible files

## Notes

- Copy operations are **asynchronous**
- The response returns a `monitor_url` to check progress
- The `monitor_url` will return status logic until complete

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 404 | Item or destination folder not found |
