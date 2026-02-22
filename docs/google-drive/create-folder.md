# Create Folder

Creates a new folder in Google Drive.

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
| `parent_folder_id` | string | No | `root` | Parent folder ID |
| `conflict_behavior` | string | No | `rename` | Conflict behavior hint (currently ignored by Google implementation) |

## Output

```json
{
  "id": "NEW456",
  "name": "New Folder",
  "item_type": "folder",
  "size": 0,
  "created_at": "2024-01-20T10:00:00Z",
  "modified_at": "2024-01-20T10:00:00Z",
  "web_url": "https://drive.google.com/..."
}
```

## Google Drive API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/files` | POST | Create folder (`mimeType=application/vnd.google-apps.folder`) |

### Query Used

- `fields=id,name,mimeType,size,quotaBytesUsed,createdTime,modifiedTime,webViewLink,webContentLink,parents`
- `supportsAllDrives=true`

## Permissions Required

- `https://www.googleapis.com/auth/drive` - Full read/write access to user Drive files

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 400 | Invalid folder name |
| 404 | Parent folder not found |
