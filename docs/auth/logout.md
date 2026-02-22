# Logout (Legacy)

Legacy documentation for an endpoint that is not currently exposed by the backend routes.

## Current Status

`POST /api/v1/auth/logout` is **not registered** in the current backend application.

## Endpoint

```
POST /api/v1/auth/logout
```

## Authentication

Required (session cookie or Bearer token).

## Input

No parameters.

## Output

```json
{
  "message": "Logged out successfully"
}
```

## Microsoft Graph API

None called.

## Permissions Required

None (only clears local session).

## Cookies Cleared

| Cookie | Description |
|--------|-------------|
| `session` | Clears the JWT session cookie |

## Notes

- This only logs out from the application
- Does not revoke Microsoft tokens
- User remains logged in to Microsoft account
