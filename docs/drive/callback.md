# Microsoft Callback

Handles the OAuth2 callback from Microsoft after user authentication.

## Endpoint

```
GET /api/v1/auth/microsoft/callback
```

## Authentication

None required (called by Microsoft redirect).

## Input

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `code` | query | Yes | Authorization code from Microsoft |
| `state` | query | Yes | State parameter for CSRF validation |

## Output

HTTP 200 with success HTML page.

## Microsoft Graph API

No Graph endpoint is called directly in this route. MSAL handles token exchange.

## Permissions Required

- `User.Read` - Read user profile

## Cookies Used/Cleared

| Cookie | Description |
|--------|-------------|
| `oauth_flow` | Read for callback validation and deleted on success |

## Errors

| Status | Description |
|--------|-------------|
| 400 | Invalid or missing code/state |
| 401 | Authentication failed |

## Flow

1. Microsoft redirects here with `code` and `state`
2. Validates and decrypts `oauth_flow` cookie
3. Exchanges `code` for access/refresh tokens
4. Creates or updates linked account with encrypted tokens
5. Returns success HTML and clears `oauth_flow`
