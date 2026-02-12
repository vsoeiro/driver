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

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user_id": "uuid",
  "microsoft_email": "user@example.com"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `access_token` | string | JWT token for API authentication |
| `token_type` | string | Always "bearer" |
| `user_id` | string | Internal user UUID |
| `microsoft_email` | string | Microsoft account email |

## Microsoft Graph API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/me` | GET | Get user profile information |

## Permissions Required

- `User.Read` - Read user profile

## Cookies Set

| Cookie | Description |
|--------|-------------|
| `session` | JWT session token (HttpOnly) |

## Errors

| Status | Description |
|--------|-------------|
| 400 | Invalid or missing code/state |
| 401 | Authentication failed |

## Flow

1. Microsoft redirects here with `code` and `state`
2. Validates `state` matches original request
3. Exchanges `code` for access/refresh tokens
4. Calls Graph API `/me` to get user info
5. Creates or updates user in database
6. Creates linked account with encrypted tokens
7. Returns JWT session token
