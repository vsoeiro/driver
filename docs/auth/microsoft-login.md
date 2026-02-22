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

HTTP 302 Redirect to Microsoft authorization URL.

## Cookies Set

| Cookie | Description |
|--------|-------------|
| `oauth_flow` | Encrypted OAuth flow payload used in callback |

## Microsoft Graph API

This endpoint does not call Graph API directly. It uses MSAL to generate the authorization URL.

## Permissions Required

None (initiates auth flow).

## Flow

1. Client calls this endpoint
2. Backend redirects user to Microsoft login page
3. User authenticates with Microsoft
4. Microsoft redirects to callback endpoint

## Example

```bash
curl http://localhost:8000/api/v1/auth/microsoft/login
```
