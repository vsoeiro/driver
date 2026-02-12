# Upload Chunk

Uploads a chunk of data to an existing upload session.

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

### Headers

```
Content-Range: bytes {start_byte}-{end_byte}/{total_size}
```

## Output

### During Upload (Progress)

```json
{
  "expirationDateTime": "2024-01-17T10:00:00Z",
  "nextExpectedRanges": ["5242880-104857599"]
}
```

### Final Chunk (Complete)

```json
{
  "id": "NEW123",
  "name": "large-video.mp4",
  "size": 104857600,
  "file": {
    "mimeType": "video/mp4"
  }
}
```

## Microsoft Graph API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `{upload_url}` | PUT | Upload chunk to session |

## Permissions Required

- `Files.ReadWrite` - Read and write user files
- `Files.ReadWrite.All` - Read and write all accessible files

## Chunk Size Rules

- Minimum: 320KB
- Recommended: 5-10MB
- Maximum: 60MB per request
- Must be multiples of 320KB (except last chunk)

## Example Flow

```
File size: 15MB

Chunk 1: bytes 0-5242879 (5MB)
Chunk 2: bytes 5242880-10485759 (5MB)
Chunk 3: bytes 10485760-15728639 (5MB) → Returns DriveItem
```

## Example (curl)

```bash
# Upload first chunk (0-5MB)
curl -X PUT \
  "http://localhost:8000/api/v1/drive/{account_id}/upload/chunk?upload_url=...&start_byte=0&end_byte=5242879&total_size=15728640" \
  -F "file=@chunk1.bin"
```

## Errors

| Status | Description |
|--------|-------------|
| 400 | Invalid byte range |
| 404 | Upload session expired or not found |
| 416 | Range not satisfiable |
