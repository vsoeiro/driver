# Create Upload Session

Creates an upload session for large files (> 4MB) uploaded in chunks.

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
| `folder_id` | string | No | `root` | Target folder ID |
| `conflict_behavior` | string | No | `rename` | Conflict behavior hint (currently ignored by Google implementation) |

## Output

```json
{
  "upload_url": "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable...",
  "expiration": "2024-01-17T10:00:00Z",
  "next_expected_ranges": []
}
```

| Field | Type | Description |
|-------|------|-------------|
| `upload_url` | string | URL to upload chunks to |
| `expiration` | datetime | Session expiration tracked by backend |
| `next_expected_ranges` | array | Byte ranges expected next |

## Google Drive API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/upload/drive/v3/files` | POST | Create resumable upload session |

### Query and Headers Used

- `uploadType=resumable`
- `supportsAllDrives=true`
- `Content-Type: application/json; charset=UTF-8`
- `X-Upload-Content-Type: application/octet-stream`

## Permissions Required

- `https://www.googleapis.com/auth/drive` - Full read/write access to user Drive files

## Upload Flow

```
1. POST /upload/session -> get upload_url
2. PUT /upload/chunk with bytes 0-5MB
3. PUT /upload/chunk with bytes 5MB-10MB
4. Repeat until complete
5. Final chunk returns file metadata
```

## Notes

- Session URL is returned in Google `Location` response header
- Current backend sets expiration as now + 1 day

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 404 | Folder not found |
| 502 | Upload session URL not returned by Google |
