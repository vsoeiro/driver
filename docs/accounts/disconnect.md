# Disconnect Account

Removes a linked Microsoft account from the user profile.

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

```json
{
  "message": "Account disconnected successfully"
}
```

## Microsoft Graph API

None called (local operation only).

## Permissions Required

None (local operation).

## Notes

- Deletes the linked account and all stored tokens
- Does not revoke tokens on Microsoft side
- Cannot delete the last/only linked account

## Errors

| Status | Description |
|--------|-------------|
| 401 | Not authenticated |
| 403 | Cannot delete primary account |
| 404 | Account not found |
