# Backend Endpoint Map

Complete inventory of endpoints exposed by the backend application.

- Total endpoints mapped: **77**
- Base API prefix for routers: `/api/v1`
- Source of truth: decorators in `src/backend/api/routes/*.py` plus app routes in `src/backend/main.py`

## Summary by Group

| Group | Count |
|-------|-------|
| `ACCOUNTS` | 3 |
| `ADMIN` | 3 |
| `AUTH` | 6 |
| `DRIVE` | 20 |
| `ITEMS` | 2 |
| `JOBS` | 16 |
| `METADATA` | 26 |
| `SYSTEM` | 1 |

## ACCOUNTS

| Method | Path | Summary | Handler | Source |
|--------|------|---------|---------|--------|
| `GET` | `/api/v1/accounts` | List all linked Microsoft accounts. | `list_linked_accounts` | `src/backend/api/routes/accounts.py:18` |
| `DELETE` | `/api/v1/accounts/{account_id}` | Disconnect (delete) a linked Microsoft account. | `disconnect_account` | `src/backend/api/routes/accounts.py:83` |
| `GET` | `/api/v1/accounts/{account_id}` | Get a specific linked account by ID. | `get_linked_account` | `src/backend/api/routes/accounts.py:59` |
## ADMIN

| Method | Path | Summary | Handler | Source |
|--------|------|---------|---------|--------|
| `GET` | `/api/v1/admin/observability` | - | `get_observability_snapshot` | `src/backend/api/routes/admin.py:21` |
| `GET` | `/api/v1/admin/settings` | - | `get_runtime_settings` | `src/backend/api/routes/admin.py:27` |
| `PUT` | `/api/v1/admin/settings` | - | `update_runtime_settings` | `src/backend/api/routes/admin.py:50` |
## AUTH

| Method | Path | Summary | Handler | Source |
|--------|------|---------|---------|--------|
| `GET` | `/api/v1/auth/dropbox/callback` | Handle Dropbox OAuth2 callback and persist linked account. | `dropbox_callback` | `src/backend/api/routes/auth.py:144` |
| `GET` | `/api/v1/auth/dropbox/login` | Initiate Dropbox OAuth2 login flow. | `dropbox_login` | `src/backend/api/routes/auth.py:52` |
| `GET` | `/api/v1/auth/google/callback` | Handle Google OAuth2 callback and persist linked account. | `google_callback` | `src/backend/api/routes/auth.py:80` |
| `GET` | `/api/v1/auth/google/login` | Initiate Google OAuth2 login flow. | `google_login` | `src/backend/api/routes/auth.py:24` |
| `GET` | `/api/v1/auth/microsoft/callback` | Handle Microsoft OAuth2 callback. | `microsoft_callback` | `src/backend/api/routes/auth.py:257` |
| `GET` | `/api/v1/auth/microsoft/login` | Initiate Microsoft OAuth2 login flow. | `microsoft_login` | `src/backend/api/routes/auth.py:212` |
## DRIVE

| Method | Path | Summary | Handler | Source |
|--------|------|---------|---------|--------|
| `POST` | `/api/v1/drive/{account_id}/download/zip` | Download multiple selected files as a ZIP archive. | `download_zip` | `src/backend/api/routes/drive.py:225` |
| `GET` | `/api/v1/drive/{account_id}/download/{item_id}` | Get a temporary download URL for a file. | `get_download_url` | `src/backend/api/routes/drive.py:131` |
| `GET` | `/api/v1/drive/{account_id}/download/{item_id}/content` | Proxy file bytes through backend so browser <img> can load provider-protected files. | `download_content` | `src/backend/api/routes/drive.py:167` |
| `GET` | `/api/v1/drive/{account_id}/download/{item_id}/redirect` | Redirect to the file download URL. | `download_redirect` | `src/backend/api/routes/drive.py:214` |
| `GET` | `/api/v1/drive/{account_id}/file/{item_id}` | Get metadata for a specific file or folder. | `get_file_metadata` | `src/backend/api/routes/drive.py:121` |
| `GET` | `/api/v1/drive/{account_id}/files` | List files in the root of OneDrive. | `list_root_files` | `src/backend/api/routes/drive.py:96` |
| `GET` | `/api/v1/drive/{account_id}/files/{item_id}` | List files in a specific folder. | `list_folder_files` | `src/backend/api/routes/drive.py:108` |
| `POST` | `/api/v1/drive/{account_id}/folders` | Create a new folder. | `create_folder` | `src/backend/api/routes/drive.py:455` |
| `POST` | `/api/v1/drive/{account_id}/items/batch-delete` | Delete multiple items (move to recycle bin). | `batch_delete_items` | `src/backend/api/routes/drive.py:554` |
| `DELETE` | `/api/v1/drive/{account_id}/items/{item_id}` | Delete an item (move to recycle bin). | `delete_item` | `src/backend/api/routes/drive.py:541` |
| `PATCH` | `/api/v1/drive/{account_id}/items/{item_id}` | Update an item (rename or move). | `update_item` | `src/backend/api/routes/drive.py:479` |
| `POST` | `/api/v1/drive/{account_id}/items/{item_id}/copy` | Copy an item. Returns the monitor URL. | `copy_item` | `src/backend/api/routes/drive.py:524` |
| `GET` | `/api/v1/drive/{account_id}/path/{item_id}` | Get the full breadcrumb path for an item. | `get_item_path` | `src/backend/api/routes/drive.py:347` |
| `GET` | `/api/v1/drive/{account_id}/quota` | Get storage quota information for the OneDrive. | `get_quota` | `src/backend/api/routes/drive.py:319` |
| `GET` | `/api/v1/drive/{account_id}/recent` | Get recently accessed files. | `get_recent_files` | `src/backend/api/routes/drive.py:329` |
| `GET` | `/api/v1/drive/{account_id}/search` | Search for files and folders in OneDrive. | `search_files` | `src/backend/api/routes/drive.py:309` |
| `GET` | `/api/v1/drive/{account_id}/shared` | Get files shared with the current user. | `get_shared_files` | `src/backend/api/routes/drive.py:338` |
| `POST` | `/api/v1/drive/{account_id}/upload` | Upload a file (up to 4MB). For larger files, use the upload session endpoint. | `upload_file` | `src/backend/api/routes/drive.py:359` |
| `PUT` | `/api/v1/drive/{account_id}/upload/chunk` | Upload a chunk to an existing upload session. | `upload_chunk` | `src/backend/api/routes/drive.py:423` |
| `POST` | `/api/v1/drive/{account_id}/upload/session` | Create an upload session for large files (> 4MB). | `create_upload_session` | `src/backend/api/routes/drive.py:404` |
## ITEMS

| Method | Path | Summary | Handler | Source |
|--------|------|---------|---------|--------|
| `GET` | `/api/v1/items` | List all items with pagination and filtering. | `list_items` | `src/backend/api/routes/items.py:97` |
| `POST` | `/api/v1/items/metadata/batch` | Batch update metadata for multiple items. | `batch_update_metadata` | `src/backend/api/routes/items.py:335` |
## JOBS

| Method | Path | Summary | Handler | Source |
|--------|------|---------|---------|--------|
| `GET` | `/api/v1/jobs/` | List recent jobs. | `list_jobs` | `src/backend/api/routes/jobs.py:108` |
| `POST` | `/api/v1/jobs/apply-metadata-recursive` | Apply metadata recursively to all items under a path prefix. | `create_apply_metadata_recursive_job` | `src/backend/api/routes/jobs.py:230` |
| `POST` | `/api/v1/jobs/apply-rule` | Create a job that applies one metadata rule. | `create_apply_rule_job` | `src/backend/api/routes/jobs.py:278` |
| `POST` | `/api/v1/jobs/comics/extract` | Create a job that extracts comic cover/page metadata for selected items/folders. | `create_extract_comic_assets_job` | `src/backend/api/routes/jobs.py:291` |
| `POST` | `/api/v1/jobs/comics/extract-library` | Create chunked jobs that map all synced .cbr/.cbz files in File Library. | `create_extract_library_comic_assets_job` | `src/backend/api/routes/jobs.py:320` |
| `POST` | `/api/v1/jobs/comics/reindex-covers` | Create a background job that re-indexes mapped comic covers using current library settings. | `create_reindex_comic_covers_job` | `src/backend/api/routes/jobs.py:305` |
| `POST` | `/api/v1/jobs/metadata-undo` | Create a job that undoes metadata changes from a batch. | `create_metadata_undo_job` | `src/backend/api/routes/jobs.py:265` |
| `POST` | `/api/v1/jobs/metadata-update` | Create a new job to bulk update metadata. | `create_metadata_update_job` | `src/backend/api/routes/jobs.py:196` |
| `POST` | `/api/v1/jobs/move` | Create a new job to move items between accounts. | `create_move_job` | `src/backend/api/routes/jobs.py:88` |
| `POST` | `/api/v1/jobs/remove-metadata-recursive` | Remove metadata from all items under a path prefix. | `create_remove_metadata_recursive_job` | `src/backend/api/routes/jobs.py:249` |
| `POST` | `/api/v1/jobs/sync` | Create a new job to sync items for an account. | `create_sync_job` | `src/backend/api/routes/jobs.py:213` |
| `POST` | `/api/v1/jobs/upload` | Upload a file to be processed in the background. | `create_upload_job` | `src/backend/api/routes/jobs.py:152` |
| `DELETE` | `/api/v1/jobs/{job_id}` | Delete one finalized job from history. | `delete_job` | `src/backend/api/routes/jobs.py:383` |
| `GET` | `/api/v1/jobs/{job_id}/attempts` | Return execution attempt history for one job. | `list_job_attempts` | `src/backend/api/routes/jobs.py:428` |
| `POST` | `/api/v1/jobs/{job_id}/cancel` | Request cancellation for a job. | `cancel_job` | `src/backend/api/routes/jobs.py:398` |
| `POST` | `/api/v1/jobs/{job_id}/reprocess` | Clone a finalized job and queue it again. | `reprocess_job` | `src/backend/api/routes/jobs.py:413` |
## METADATA

| Method | Path | Summary | Handler | Source |
|--------|------|---------|---------|--------|
| `DELETE` | `/api/v1/metadata/attributes/{attribute_id}` | Delete a metadata attribute. | `delete_attribute` | `src/backend/api/routes/metadata.py:1137` |
| `PATCH` | `/api/v1/metadata/attributes/{attribute_id}` | Update a metadata attribute. | `update_attribute` | `src/backend/api/routes/metadata.py:1150` |
| `POST` | `/api/v1/metadata/batches/{batch_id}/undo` | Undo metadata changes from a batch id. | `undo_metadata_batch_route` | `src/backend/api/routes/metadata.py:1451` |
| `GET` | `/api/v1/metadata/categories` | List all metadata categories with their attributes. | `list_categories` | `src/backend/api/routes/metadata.py:639` |
| `POST` | `/api/v1/metadata/categories` | Create a new metadata category. | `create_category` | `src/backend/api/routes/metadata.py:1067` |
| `GET` | `/api/v1/metadata/categories/stats` | Return each category with its item count. | `get_category_stats` | `src/backend/api/routes/metadata.py:653` |
| `DELETE` | `/api/v1/metadata/categories/{category_id}` | Delete a metadata category. | `delete_category` | `src/backend/api/routes/metadata.py:1095` |
| `POST` | `/api/v1/metadata/categories/{category_id}/attributes` | Add an attribute to a category. | `create_attribute` | `src/backend/api/routes/metadata.py:1117` |
| `GET` | `/api/v1/metadata/categories/{category_id}/series-summary` | Return one-page summary grouped by comic series for Series view. | `get_category_series_summary` | `src/backend/api/routes/metadata.py:798` |
| `POST` | `/api/v1/metadata/items` | Assign or update metadata for an item. | `upsert_item_metadata` | `src/backend/api/routes/metadata.py:1247` |
| `POST` | `/api/v1/metadata/items/batch-delete` | Remove metadata for multiple items. | `batch_delete_item_metadata` | `src/backend/api/routes/metadata.py:1397` |
| `DELETE` | `/api/v1/metadata/items/{account_id}/{item_id}` | Remove metadata from an item. | `delete_item_metadata` | `src/backend/api/routes/metadata.py:1372` |
| `GET` | `/api/v1/metadata/items/{account_id}/{item_id}` | Get metadata for a specific item. | `get_item_metadata` | `src/backend/api/routes/metadata.py:1176` |
| `PATCH` | `/api/v1/metadata/items/{account_id}/{item_id}/attributes/{attribute_id}` | Update one metadata attribute value for one item. | `update_item_metadata_attribute` | `src/backend/api/routes/metadata.py:1191` |
| `GET` | `/api/v1/metadata/items/{account_id}/{item_id}/history` | List metadata change history for one item. | `get_item_metadata_history` | `src/backend/api/routes/metadata.py:1431` |
| `GET` | `/api/v1/metadata/layouts` | - | `list_metadata_form_layouts` | `src/backend/api/routes/metadata.py:717` |
| `GET` | `/api/v1/metadata/layouts/{category_id}` | - | `get_metadata_form_layout` | `src/backend/api/routes/metadata.py:730` |
| `PUT` | `/api/v1/metadata/layouts/{category_id}` | - | `upsert_metadata_form_layout` | `src/backend/api/routes/metadata.py:752` |
| `GET` | `/api/v1/metadata/libraries` | List metadata libraries. | `list_metadata_libraries` | `src/backend/api/routes/metadata.py:1596` |
| `POST` | `/api/v1/metadata/libraries/{library_key}/activate` | Activate a metadata library and ensure managed schema exists. | `activate_metadata_library` | `src/backend/api/routes/metadata.py:1604` |
| `POST` | `/api/v1/metadata/libraries/{library_key}/deactivate` | Deactivate a metadata library. | `deactivate_metadata_library` | `src/backend/api/routes/metadata.py:1627` |
| `GET` | `/api/v1/metadata/rules` | List metadata rules by priority. | `list_metadata_rules` | `src/backend/api/routes/metadata.py:1462` |
| `POST` | `/api/v1/metadata/rules` | Create a metadata rule. | `create_metadata_rule` | `src/backend/api/routes/metadata.py:1470` |
| `POST` | `/api/v1/metadata/rules/preview` | Preview how many items would be changed by a rule. | `preview_metadata_rule` | `src/backend/api/routes/metadata.py:1539` |
| `DELETE` | `/api/v1/metadata/rules/{rule_id}` | Delete a metadata rule. | `delete_metadata_rule` | `src/backend/api/routes/metadata.py:1526` |
| `PATCH` | `/api/v1/metadata/rules/{rule_id}` | Update a metadata rule. | `update_metadata_rule` | `src/backend/api/routes/metadata.py:1489` |
## SYSTEM

| Method | Path | Summary | Handler | Source |
|--------|------|---------|---------|--------|
| `GET` | `/health` | Health check endpoint. | `health_check` | `src/backend/main.py:118` |
