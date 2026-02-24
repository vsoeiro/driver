# Google Login

Initiates the Google OAuth2 authorization flow.

## Endpoint

```
GET /api/v1/auth/google/login
```

## Authentication

None required (public endpoint).

## Input

No parameters.

## Output

HTTP 302 Redirect to Google authorization URL.

## Cookies Set

| Cookie | Description |
|--------|-------------|
| `oauth_google_state` | Encrypted state used for CSRF validation in callback |

## Google OAuth API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `https://accounts.google.com/o/oauth2/v2/auth` | GET | OAuth authorization endpoint |

## Permissions Requested

- `openid`
- `email`
- `profile`
- `https://www.googleapis.com/auth/drive`

## Notes

- Returns `503` when Google OAuth credentials are not configured.
- Redirect URI used is `GOOGLE_REDIRECT_URI` from application settings.

## Errors

| Status | Description |
|--------|-------------|
| 503 | Google OAuth is not configured |

