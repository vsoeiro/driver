# Download Redirect

Redirects the browser directly to the file download.

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
| `item_id` | string | path | Yes | OneDrive file ID |

## Output

HTTP 302 Redirect to the download URL.

## Microsoft Graph API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/me/drive/items/{item_id}` | GET | Get item with download URL |

## Permissions Required

- `Files.Read` - Read user files
- `Files.Read.All` - Read all accessible files

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
