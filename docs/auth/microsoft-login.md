# Microsoft Login

Initiates the Microsoft OAuth2 authorization flow.

## Endpoint

```
GET /api/v1/auth/microsoft/login
```

## Authentication

None required (public endpoint).

## Input

No parameters.

## Output

```json
{
  "auth_url": "https://login.microsoftonline.com/...",
  "state": "abc123..."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `auth_url` | string | URL to redirect user for Microsoft login |
| `state` | string | CSRF protection state parameter |

## Microsoft Graph API

This endpoint does not call Graph API directly. It uses MSAL to generate the authorization URL.

## Permissions Required

None (initiates auth flow).

## Flow

1. Client calls this endpoint
2. Receives `auth_url`
3. Redirects user to `auth_url`
4. User authenticates with Microsoft
5. Microsoft redirects to callback endpoint

## Example

```bash
curl http://localhost:8000/api/v1/auth/microsoft/login
```
