# Copy Item

Copies a file or folder to a new location in Dropbox.

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
| `parent_folder_id` | string | No | `root` | Destination folder ID |

## Output

```json
{
  "monitor_url": "https://www.dropbox.com/home/file/d/..."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `monitor_url` | string | For Google, contains `webViewLink` of copied item (or fallback item ID) |

## Dropbox API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/files/{item_id}/copy` | POST | Copy item |

### Query Used

- `fields=id,webViewLink`
- `supportsAllDrives=true`

## Permissions Required

- `account_info.read + files.metadata.read + files.content.read + files.content.write` - Full read/write access to user Drive files

## Notes

- Google copy is handled synchronously
- The API still returns field name `monitor_url` for compatibility

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 404 | Item or destination folder not found |
