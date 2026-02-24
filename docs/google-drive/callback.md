# Google Callback

Handles the OAuth2 callback from Google after user authentication.

## Endpoint

```
GET /api/v1/auth/google/callback
```

## Authentication

None required (called by Google redirect).

## Input

| Parameter | Type | Location | Required | Description |
|-----------|------|----------|----------|-------------|
| `code` | string | query | Yes | Authorization code from Google |
| `state` | string | query | Yes | State parameter for CSRF validation |

## Output

HTTP 200 with success HTML page.

## Cookies Used/Cleared

| Cookie | Description |
|--------|-------------|
| `oauth_google_state` | Read for CSRF validation and deleted on success |

## Google OAuth API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `https://oauth2.googleapis.com/token` | POST | Exchange authorization code for tokens |

## Side Effects

- Creates or updates a linked account with provider `google`.
- Stores encrypted access token and refresh token.
- Updates linked account profile (`provider_account_id`, `email`, `display_name`).

## Errors

| Status | Description |
|--------|-------------|
| 400 | Invalid or missing state/callback session |
| 401 | Failed to authenticate with Google |

