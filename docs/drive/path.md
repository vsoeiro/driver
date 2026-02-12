# Get Item Path

Returns the full breadcrumb path for an item.

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
| `item_id` | string | path | Yes | OneDrive item ID |

## Output

```json
{
  "breadcrumb": [
    {"id": "", "name": "Documents"},
    {"id": "", "name": "Projects"},
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
| `id` | string | Item ID (empty for parent folders) |
| `name` | string | Folder or file name |

## Microsoft Graph API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/me/drive/items/{item_id}?$select=id,name,parentReference` | GET | Get item with parent info |

## Permissions Required

- `Files.Read` - Read user files

## Use Cases

- Navigation breadcrumbs in UI
- Display current location in file explorer
- Build folder hierarchy

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 404 | Item not found |
