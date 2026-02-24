# Get Item Path

Returns the full breadcrumb path for a Dropbox item.

## Endpoint

```
GET /api/v1/drive/{account_id}/path/{item_id}
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
  "breadcrumb": [
    {"id": "root", "name": "Root"},
    {"id": "FOLDER_1", "name": "Documents"},
    {"id": "FOLDER_2", "name": "Projects"},
    {"id": "ABC123", "name": "Report.docx"}
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `breadcrumb` | array | Path components from root to item |

### Breadcrumb Item

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Item ID |
| `name` | string | Folder or file name |

## Dropbox API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/files/{item_id}` | GET | Resolve item and parents recursively |

### Query Used

- `fields=id,name,parents`
- `supportsAllDrives=true`

## Permissions Required

- `account_info.read + files.metadata.read + files.content.read + files.content.write` - Full read/write access to user Drive files

## Use Cases

- Navigation breadcrumbs in UI
- Display current location in file explorer
- Build folder hierarchy

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 404 | Item not found |
