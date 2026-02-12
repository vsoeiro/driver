# Create Folder

Creates a new folder in OneDrive.

## Endpoint

```
POST /api/v1/drive/{account_id}/folders
```

## Authentication

Required (session cookie or Bearer token).

## Input

| Parameter | Type | Location | Required | Description |
|-----------|------|----------|----------|-------------|
| `account_id` | string | path | Yes | UUID of the linked account |

### Request Body

```json
{
  "name": "New Folder",
  "parent_folder_id": "root",
  "conflict_behavior": "rename"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | - | Folder name |
| `parent_folder_id` | string | No | "root" | Parent folder ID |
| `conflict_behavior` | string | No | "rename" | Action if folder exists |

## Output

```json
{
  "id": "NEW456",
  "name": "New Folder",
  "item_type": "folder",
  "child_count": 0,
  "created_at": "2024-01-20T10:00:00Z",
  "modified_at": "2024-01-20T10:00:00Z",
  "web_url": "https://onedrive.live.com/..."
}
```

## Microsoft Graph API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/me/drive/items/{parent_id}/children` | POST | Create new child item |

## Permissions Required

- `Files.ReadWrite` - Read and write user files
- `Files.ReadWrite.All` - Read and write all accessible files

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 400 | Invalid folder name |
| 409 | Folder exists (if conflict_behavior=fail) |
| 404 | Parent folder not found |
