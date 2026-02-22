# Upload Chunk

Uploads a chunk of data to an existing Google Drive upload session.

## Endpoint

```
PUT /api/v1/drive/{account_id}/upload/chunk
```

## Authentication

Required (session cookie or Bearer token).

## Input

| Parameter | Type | Location | Required | Description |
|-----------|------|----------|----------|-------------|
| `account_id` | string | path | Yes | UUID of the linked account |
| `upload_url` | string | query | Yes | Upload session URL |
| `start_byte` | integer | query | Yes | Start byte position |
| `end_byte` | integer | query | Yes | End byte position |
| `total_size` | integer | query | Yes | Total file size |
| `file` | file | form-data | Yes | Chunk data |

### Headers Sent to Google

```
Content-Range: bytes {start_byte}-{end_byte}/{total_size}
Content-Length: {chunk_size}
```

## Output

### During Upload (Progress)

```json
{
  "next_expected_ranges": ["5242880-"]
}
```

### Final Chunk (Complete)

```json
{
  "id": "NEW123",
  "name": "large-video.mp4",
  "mimeType": "video/mp4"
}
```

## Google Drive API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `{upload_url}` | PUT | Upload chunk to resumable session URL |

## Permissions Required

- `https://www.googleapis.com/auth/drive` - Full read/write access to user Drive files

## Chunk Rules

- Chunks must be sent in order
- Last response with status `308` means upload is still in progress
- Final response returns uploaded file metadata

## Example Flow

```
File size: 15MB

Chunk 1: bytes 0-5242879 (5MB)
Chunk 2: bytes 5242880-10485759 (5MB)
Chunk 3: bytes 10485760-15728639 (5MB) -> Returns file metadata
```

## Errors

| Status | Description |
|--------|-------------|
| 400 | Invalid byte range or chunk payload |
| 404 | Upload session expired or not found |
| 5xx | Google upload failure |
