# API Documentation

This folder contains detailed documentation for all Drive Organizer API endpoints.

## Endpoints

### Authentication
- [Microsoft Login](./auth/microsoft-login.md)
- [Microsoft Callback](./auth/microsoft-callback.md)
- [Logout](./auth/logout.md)
- [Get Current User](./auth/me.md)

### Accounts
- [List Linked Accounts](./accounts/list.md)
- [Disconnect Account](./accounts/disconnect.md)

### OneDrive
- [List Root Files](./drive/list-root.md)
- [List Folder Files](./drive/list-folder.md)
- [Get File Metadata](./drive/get-metadata.md)
- [Get Download URL](./drive/download-url.md)
- [Download Redirect](./drive/download-redirect.md)
- [Search Files](./drive/search.md)
- [Get Quota](./drive/quota.md)
- [Get Recent Files](./drive/recent.md)
- [Get Shared Files](./drive/shared.md)
- [Get Item Path](./drive/path.md)
- [Upload File](./drive/upload.md)
- [Create Upload Session](./drive/upload-session.md)
- [Upload Chunk](./drive/upload-chunk.md)
- [Create Folder](./drive/create-folder.md)
- [Update Item (Rename/Move)](./drive/update-item.md)
- [Copy Item](./drive/copy-item.md)
- [Delete Item](./drive/delete-item.md)

## Microsoft Graph API Permissions

| Permission | Type | Description |
|------------|------|-------------|
| `User.Read` | Delegated | Read user profile |
| `Files.Read` | Delegated | Read user files |
| `Files.Read.All` | Delegated | Read all files user can access |
| `Files.ReadWrite` | Delegated | Read and write user files |
| `Files.ReadWrite.All` | Delegated | Read and write all files user can access |
