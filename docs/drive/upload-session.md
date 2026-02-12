# Create Upload Session

Creates an upload session for uploading large files (> 4MB) in chunks.

## Endpoint

```
POST /api/v1/drive/{account_id}/upload/session
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
  "filename": "large-video.mp4",
  "file_size": 104857600,
  "folder_id": "root",
  "conflict_behavior": "rename"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `filename` | string | Yes | - | Name of the file |
| `file_size` | integer | Yes | - | Total file size in bytes |
| `folder_id` | string | No | "root" | Target folder ID |
| `conflict_behavior` | string | No | "rename" | Action if file exists |

### Conflict Behaviors

| Value | Description |
|-------|-------------|
| `rename` | Add suffix to filename (e.g., "file (1).pdf") |
| `replace` | Overwrite existing file |
| `fail` | Return error if file exists |

## Output

```json
{
  "upload_url": "https://api.onedrive.com/...",
  "expiration": "2024-01-17T10:00:00Z",
  "next_expected_ranges": []
}
```

| Field | Type | Description |
|-------|------|-------------|
| `upload_url` | string | URL to upload chunks to |
| `expiration` | datetime | When session expires |
| `next_expected_ranges` | array | Byte ranges expected next |

## Microsoft Graph API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/me/drive/root:/{filename}:/createUploadSession` | POST | Create session |
| `/me/drive/items/{folder_id}:/{filename}:/createUploadSession` | POST | Create in folder |

## Permissions Required

- `Files.ReadWrite` - Read and write user files
- `Files.ReadWrite.All` - Read and write all accessible files

## Upload Flow

```
1. POST /upload/session → Get upload_url
2. PUT /upload/chunk with bytes 0-5MB
3. PUT /upload/chunk with bytes 5MB-10MB
4. ... repeat until complete
5. Final chunk returns DriveItem
```

## Notes

- Sessions expire after ~7 days
- Upload in chunks of 5-10MB recommended
- Chunks must be multiples of 320KB (except last)

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 409 | File exists (when conflict_behavior=fail) |
| 404 | Folder not found |
