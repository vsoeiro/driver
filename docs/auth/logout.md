# Logout

Logs out the current user by clearing the session cookie.

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
