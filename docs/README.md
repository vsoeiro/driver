# API Documentation

This folder contains detailed documentation for all Drive Organizer API endpoints.

## Endpoints

### Complete Backend Map
- [All Backend Endpoints](./endpoints.md)
- Includes `auth`, `accounts`, `drive`, `items`, `jobs`, `metadata`, `admin`, `ai`, and `/health`.

### Authentication
- [Google Login](./auth/google-login.md)
- [Google Callback](./auth/google-callback.md)
- [Microsoft Login](./auth/microsoft-login.md)
- [Microsoft Callback](./auth/microsoft-callback.md)

### Legacy Auth (Not Exposed)
- [Logout (Legacy)](./auth/logout.md)
- [Get Current User (Legacy)](./auth/me.md)

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

### Google Drive
- [List Root Files](./google-drive/list-root.md)
- [List Folder Files](./google-drive/list-folder.md)
- [Get File Metadata](./google-drive/get-metadata.md)
- [Get Download URL](./google-drive/download-url.md)
- [Download Redirect](./google-drive/download-redirect.md)
- [Search Files](./google-drive/search.md)
- [Get Quota](./google-drive/quota.md)
- [Get Recent Files](./google-drive/recent.md)
- [Get Shared Files](./google-drive/shared.md)
- [Get Item Path](./google-drive/path.md)
- [Upload File](./google-drive/upload.md)
- [Create Upload Session](./google-drive/upload-session.md)
- [Upload Chunk](./google-drive/upload-chunk.md)
- [Create Folder](./google-drive/create-folder.md)
- [Update Item (Rename/Move)](./google-drive/update-item.md)
- [Copy Item](./google-drive/copy-item.md)
- [Delete Item](./google-drive/delete-item.md)

## Microsoft Graph API Permissions

| Permission | Type | Description |
|------------|------|-------------|
| `User.Read` | Delegated | Read user profile |
| `Files.Read` | Delegated | Read user files |
| `Files.Read.All` | Delegated | Read all files user can access |
| `Files.ReadWrite` | Delegated | Read and write user files |
| `Files.ReadWrite.All` | Delegated | Read and write all files user can access |

## Google API Permissions

| Permission | Type | Description |
|------------|------|-------------|
| `openid` | OAuth scope | OpenID Connect authentication |
| `email` | OAuth scope | Access user email in ID token claims |
| `profile` | OAuth scope | Access basic profile data |
| `https://www.googleapis.com/auth/drive` | OAuth scope | Full read/write access to Google Drive files |
