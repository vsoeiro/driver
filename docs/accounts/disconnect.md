# Disconnect Account

Removes a linked account from the user profile.

## Endpoint

```
DELETE /api/v1/accounts/{account_id}
```

## Authentication

Required (session cookie or Bearer token).

## Input

| Parameter | Type | Location | Required | Description |
|-----------|------|----------|----------|-------------|
| `account_id` | string | path | Yes | UUID of the account to disconnect |

## Output

HTTP 204 No Content.

## Provider API

None called (local operation only).

## Permissions Required

None (local operation).

## Notes

- Deletes the linked account and all stored tokens
- Does not revoke tokens on provider side

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 404 | Account not found |
