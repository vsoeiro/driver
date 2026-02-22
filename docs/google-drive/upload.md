# Upload File

Uploads a small file (up to 4MB) directly to Google Drive.

## Endpoint

```
POST /api/v1/drive/{account_id}/upload
```

## Authentication

Required (session cookie or Bearer token).

## Input

| Parameter | Type | Location | Required | Description |
|-----------|------|----------|----------|-------------|
| `account_id` | string | path | Yes | UUID of the linked account |
| `file` | file | form-data | Yes | File to upload |
| `folder_id` | string | query | No | Target folder ID (default: `root`) |

### Form Data

```
Content-Type: multipart/form-data

file: <binary file data>
```

## Output

```json
{
  "id": "NEW123",
  "name": "uploaded-file.pdf",
  "item_type": "file",
  "size": 102400,
  "mime_type": "application/pdf",
  "created_at": "2024-01-16T10:00:00Z",
  "modified_at": "2024-01-16T10:00:00Z",
  "web_url": "https://drive.google.com/..."
}
```

## Google Drive API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/upload/drive/v3/files` | POST | Multipart upload (metadata + bytes) |

### Query Used

- `uploadType=multipart`
- `fields=id,name,mimeType,size,quotaBytesUsed,createdTime,modifiedTime,webViewLink,webContentLink,parents`
- `supportsAllDrives=true`

## Permissions Required

- `https://www.googleapis.com/auth/drive` - Full read/write access to user Drive files

## Limitations

- Maximum file size: 4MB
- For larger files, use the upload session endpoint

## Example (curl)

```bash
curl -X POST \
  "http://localhost:8000/api/v1/drive/{account_id}/upload?folder_id=root" \
  -H "Cookie: session=..." \
  -F "file=@/path/to/file.pdf"
```

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 413 | File too large (> 4MB) |
| 404 | Folder not found |
