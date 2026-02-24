# Dropbox Callback

Handles the OAuth2 callback from Dropbox after user authentication.

## Endpoint

```
GET /api/v1/auth/dropbox/callback
```

## Authentication

None required (called by Dropbox redirect).

## Input

| Parameter | Type | Location | Required | Description |
|-----------|------|----------|----------|-------------|
| `code` | string | query | Yes | Authorization code from Dropbox |
| `state` | string | query | Yes | State parameter for CSRF validation |

## Output

HTTP 200 with success HTML page.

## Cookies Used/Cleared

| Cookie | Description |
|--------|-------------|
| `oauth_dropbox_state` | Read for CSRF validation and deleted on success |

## Dropbox OAuth/API Calls

| Endpoint | Method | Description |
|----------|--------|-------------|
| `https://api.dropboxapi.com/oauth2/token` | POST | Exchange authorization code for tokens |
| `https://api.dropboxapi.com/2/users/get_current_account` | POST | Fetch account profile data |

## Side Effects

- Creates or updates a linked account with provider `dropbox`.
- Stores encrypted access token and refresh token.
- Updates linked account profile (`provider_account_id`, `email`, `display_name`).

## Errors

| Status | Description |
|--------|-------------|
| 400 | Invalid or missing state/callback session |
| 401 | Failed to authenticate with Dropbox |
