# Dropbox Login

Initiates the Dropbox OAuth2 authorization flow.

## Endpoint

```
GET /api/v1/auth/dropbox/login
```

## Authentication

None required (public endpoint).

## Input

No parameters.

## Output

HTTP 302 Redirect to Dropbox authorization URL.

## Cookies Set

| Cookie | Description |
|--------|-------------|
| `oauth_dropbox_state` | Encrypted state used for CSRF validation in callback |

## Dropbox OAuth API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `https://www.dropbox.com/oauth2/authorize` | GET | OAuth authorization endpoint |

## Notes

- Returns `503` when Dropbox OAuth credentials are not configured.
- Redirect URI used is `DROPBOX_REDIRECT_URI` from application settings.
- Uses `token_access_type=offline` to request refresh token support.

## Errors

| Status | Description |
|--------|-------------|
| 503 | Dropbox OAuth is not configured |
