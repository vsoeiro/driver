# Download Redirect

Redirects the browser directly to the Google Drive file download URL.

## Endpoint

```
GET /api/v1/drive/{account_id}/download/{item_id}/redirect
```

## Authentication

Required (session cookie or Bearer token).

## Input

| Parameter | Type | Location | Required | Description |
|-----------|------|----------|----------|-------------|
| `account_id` | string | path | Yes | UUID of the linked account |
| `item_id` | string | path | Yes | Google Drive file ID |

## Output

HTTP 302 Redirect to the download URL.

## Google Drive API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/files/{item_id}` | GET | Get item with `webContentLink` |

### Query Used

- `fields=id,name,mimeType,webContentLink`
- `supportsAllDrives=true`

## Permissions Required

- `https://www.googleapis.com/auth/drive` - Full read/write access to user Drive files

## Usage

Use this endpoint directly in browser or `<a>` tags:

```html
<a href="/api/v1/drive/{account_id}/download/{item_id}/redirect">Download</a>
```

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 404 | Account or file not found |
| 400 | Native Google Docs file (no direct download URL) |
