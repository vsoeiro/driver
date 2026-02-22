# Backend Endpoint Map

Complete inventory of endpoints exposed by the backend application.

- Total endpoints mapped: **82**
- Base API prefix for routers: `/api/v1`
- Source of truth: decorators in `backend/api/routes/*.py` plus app routes in `backend/main.py`

## Summary by Group

| Group | Count |
|-------|-------|
| `ACCOUNTS` | 3 |
| `ADMIN` | 3 |
| `AI` | 4 |
| `AUTH` | 4 |
| `DRIVE` | 20 |
| `ITEMS` | 2 |
| `JOBS` | 16 |
| `METADATA` | 29 |
| `SYSTEM` | 1 |

## ACCOUNTS

| Method | Path | Summary | Handler | Source |
|--------|------|---------|---------|--------|
| `GET` | `/api/v1/accounts` | List all linked Microsoft accounts. | `list_linked_accounts` | `backend/api/routes/accounts.py:18` |
| `DELETE` | `/api/v1/accounts/{account_id}` | Disconnect (delete) a linked Microsoft account. | `disconnect_account` | `backend/api/routes/accounts.py:83` |
| `GET` | `/api/v1/accounts/{account_id}` | Get a specific linked account by ID. | `get_linked_account` | `backend/api/routes/accounts.py:59` |
## ADMIN

| Method | Path | Summary | Handler | Source |
|--------|------|---------|---------|--------|
| `GET` | `/api/v1/admin/observability` | - | `get_observability_snapshot` | `backend/api/routes/admin.py:21` |
| `GET` | `/api/v1/admin/settings` | - | `get_runtime_settings` | `backend/api/routes/admin.py:27` |
| `PUT` | `/api/v1/admin/settings` | - | `update_runtime_settings` | `backend/api/routes/admin.py:56` |
## AI

| Method | Path | Summary | Handler | Source |
|--------|------|---------|---------|--------|
| `POST` | `/api/v1/ai/extract-metadata` | - | `extract_metadata` | `backend/api/routes/ai.py:96` |
| `GET` | `/api/v1/ai/health` | - | `ai_health` | `backend/api/routes/ai.py:29` |
| `POST` | `/api/v1/ai/suggest-category-schema` | - | `suggest_category_schema` | `backend/api/routes/ai.py:42` |
| `POST` | `/api/v1/ai/suggest-comic-metadata` | - | `suggest_comic_metadata` | `backend/api/routes/ai.py:121` |
## AUTH

| Method | Path | Summary | Handler | Source |
|--------|------|---------|---------|--------|
| `GET` | `/api/v1/auth/google/callback` | Handle Google OAuth2 callback and persist linked account. | `google_callback` | `backend/api/routes/auth.py:49` |
| `GET` | `/api/v1/auth/google/login` | Initiate Google OAuth2 login flow. | `google_login` | `backend/api/routes/auth.py:21` |
| `GET` | `/api/v1/auth/microsoft/callback` | Handle Microsoft OAuth2 callback. | `microsoft_callback` | `backend/api/routes/auth.py:155` |
| `GET` | `/api/v1/auth/microsoft/login` | Initiate Microsoft OAuth2 login flow. | `microsoft_login` | `backend/api/routes/auth.py:111` |
## DRIVE

| Method | Path | Summary | Handler | Source |
|--------|------|---------|---------|--------|
| `POST` | `/api/v1/drive/{account_id}/download/zip` | Download multiple selected files as a ZIP archive. | `download_zip` | `backend/api/routes/drive.py:225` |
| `GET` | `/api/v1/drive/{account_id}/download/{item_id}` | Get a temporary download URL for a file. | `get_download_url` | `backend/api/routes/drive.py:131` |
| `GET` | `/api/v1/drive/{account_id}/download/{item_id}/content` | Proxy file bytes through backend so browser <img> can load provider-protected files. | `download_content` | `backend/api/routes/drive.py:167` |
| `GET` | `/api/v1/drive/{account_id}/download/{item_id}/redirect` | Redirect to the file download URL. | `download_redirect` | `backend/api/routes/drive.py:214` |
| `GET` | `/api/v1/drive/{account_id}/file/{item_id}` | Get metadata for a specific file or folder. | `get_file_metadata` | `backend/api/routes/drive.py:121` |
| `GET` | `/api/v1/drive/{account_id}/files` | List files in the root of OneDrive. | `list_root_files` | `backend/api/routes/drive.py:96` |
| `GET` | `/api/v1/drive/{account_id}/files/{item_id}` | List files in a specific folder. | `list_folder_files` | `backend/api/routes/drive.py:108` |
| `POST` | `/api/v1/drive/{account_id}/folders` | Create a new folder. | `create_folder` | `backend/api/routes/drive.py:455` |
| `POST` | `/api/v1/drive/{account_id}/items/batch-delete` | Delete multiple items (move to recycle bin). | `batch_delete_items` | `backend/api/routes/drive.py:554` |
| `DELETE` | `/api/v1/drive/{account_id}/items/{item_id}` | Delete an item (move to recycle bin). | `delete_item` | `backend/api/routes/drive.py:541` |
| `PATCH` | `/api/v1/drive/{account_id}/items/{item_id}` | Update an item (rename or move). | `update_item` | `backend/api/routes/drive.py:479` |
| `POST` | `/api/v1/drive/{account_id}/items/{item_id}/copy` | Copy an item. Returns the monitor URL. | `copy_item` | `backend/api/routes/drive.py:524` |
| `GET` | `/api/v1/drive/{account_id}/path/{item_id}` | Get the full breadcrumb path for an item. | `get_item_path` | `backend/api/routes/drive.py:347` |
| `GET` | `/api/v1/drive/{account_id}/quota` | Get storage quota information for the OneDrive. | `get_quota` | `backend/api/routes/drive.py:319` |
| `GET` | `/api/v1/drive/{account_id}/recent` | Get recently accessed files. | `get_recent_files` | `backend/api/routes/drive.py:329` |
| `GET` | `/api/v1/drive/{account_id}/search` | Search for files and folders in OneDrive. | `search_files` | `backend/api/routes/drive.py:309` |
| `GET` | `/api/v1/drive/{account_id}/shared` | Get files shared with the current user. | `get_shared_files` | `backend/api/routes/drive.py:338` |
| `POST` | `/api/v1/drive/{account_id}/upload` | Upload a file (up to 4MB). For larger files, use the upload session endpoint. | `upload_file` | `backend/api/routes/drive.py:359` |
| `PUT` | `/api/v1/drive/{account_id}/upload/chunk` | Upload a chunk to an existing upload session. | `upload_chunk` | `backend/api/routes/drive.py:423` |
| `POST` | `/api/v1/drive/{account_id}/upload/session` | Create an upload session for large files (> 4MB). | `create_upload_session` | `backend/api/routes/drive.py:404` |
## ITEMS

| Method | Path | Summary | Handler | Source |
|--------|------|---------|---------|--------|
| `GET` | `/api/v1/items` | List all items with pagination and filtering. | `list_items` | `backend/api/routes/items.py:97` |
| `POST` | `/api/v1/items/metadata/batch` | Batch update metadata for multiple items. | `batch_update_metadata` | `backend/api/routes/items.py:336` |
## JOBS

| Method | Path | Summary | Handler | Source |
|--------|------|---------|---------|--------|
| `GET` | `/api/v1/jobs/` | List recent jobs. | `list_jobs` | `backend/api/routes/jobs.py:108` |
| `POST` | `/api/v1/jobs/apply-metadata-recursive` | Apply metadata recursively to all items under a path prefix. | `create_apply_metadata_recursive_job` | `backend/api/routes/jobs.py:230` |
| `POST` | `/api/v1/jobs/apply-rule` | Create a job that applies one metadata rule. | `create_apply_rule_job` | `backend/api/routes/jobs.py:278` |
| `POST` | `/api/v1/jobs/comics/extract` | Create a job that extracts comic cover/page metadata for selected items/folders. | `create_extract_comic_assets_job` | `backend/api/routes/jobs.py:291` |
| `POST` | `/api/v1/jobs/comics/extract-library` | Create chunked jobs that map all synced .cbr/.cbz files in File Library. | `create_extract_library_comic_assets_job` | `backend/api/routes/jobs.py:320` |
| `POST` | `/api/v1/jobs/comics/reindex-covers` | Create a background job that re-indexes mapped comic covers using current plugin settings. | `create_reindex_comic_covers_job` | `backend/api/routes/jobs.py:305` |
| `POST` | `/api/v1/jobs/metadata-undo` | Create a job that undoes metadata changes from a batch. | `create_metadata_undo_job` | `backend/api/routes/jobs.py:265` |
| `POST` | `/api/v1/jobs/metadata-update` | Create a new job to bulk update metadata. | `create_metadata_update_job` | `backend/api/routes/jobs.py:196` |
| `POST` | `/api/v1/jobs/move` | Create a new job to move items between accounts. | `create_move_job` | `backend/api/routes/jobs.py:88` |
| `POST` | `/api/v1/jobs/remove-metadata-recursive` | Remove metadata from all items under a path prefix. | `create_remove_metadata_recursive_job` | `backend/api/routes/jobs.py:249` |
| `POST` | `/api/v1/jobs/sync` | Create a new job to sync items for an account. | `create_sync_job` | `backend/api/routes/jobs.py:213` |
| `POST` | `/api/v1/jobs/upload` | Upload a file to be processed in the background. | `create_upload_job` | `backend/api/routes/jobs.py:152` |
| `DELETE` | `/api/v1/jobs/{job_id}` | Delete one finalized job from history. | `delete_job` | `backend/api/routes/jobs.py:383` |
| `GET` | `/api/v1/jobs/{job_id}/attempts` | Return execution attempt history for one job. | `list_job_attempts` | `backend/api/routes/jobs.py:428` |
| `POST` | `/api/v1/jobs/{job_id}/cancel` | Request cancellation for a job. | `cancel_job` | `backend/api/routes/jobs.py:398` |
| `POST` | `/api/v1/jobs/{job_id}/reprocess` | Clone a finalized job and queue it again. | `reprocess_job` | `backend/api/routes/jobs.py:413` |
## METADATA

| Method | Path | Summary | Handler | Source |
|--------|------|---------|---------|--------|
| `DELETE` | `/api/v1/metadata/attributes/{attribute_id}` | Delete a metadata attribute. | `delete_attribute` | `backend/api/routes/metadata.py:1187` |
| `PATCH` | `/api/v1/metadata/attributes/{attribute_id}` | Update a metadata attribute. | `update_attribute` | `backend/api/routes/metadata.py:1200` |
| `POST` | `/api/v1/metadata/batches/{batch_id}/undo` | Undo metadata changes from a batch id. | `undo_metadata_batch_route` | `backend/api/routes/metadata.py:1617` |
| `GET` | `/api/v1/metadata/categories` | List all metadata categories with their attributes. | `list_categories` | `backend/api/routes/metadata.py:689` |
| `POST` | `/api/v1/metadata/categories` | Create a new metadata category. | `create_category` | `backend/api/routes/metadata.py:1117` |
| `GET` | `/api/v1/metadata/categories/stats` | Return each category with its item count. | `get_category_stats` | `backend/api/routes/metadata.py:703` |
| `DELETE` | `/api/v1/metadata/categories/{category_id}` | Delete a metadata category. | `delete_category` | `backend/api/routes/metadata.py:1145` |
| `POST` | `/api/v1/metadata/categories/{category_id}/attributes` | Add an attribute to a category. | `create_attribute` | `backend/api/routes/metadata.py:1167` |
| `GET` | `/api/v1/metadata/categories/{category_id}/series-summary` | Return one-page summary grouped by comic series for Series view. | `get_category_series_summary` | `backend/api/routes/metadata.py:848` |
| `POST` | `/api/v1/metadata/items` | Assign or update metadata for an item. | `upsert_item_metadata` | `backend/api/routes/metadata.py:1297` |
| `POST` | `/api/v1/metadata/items/batch-delete` | Remove metadata for multiple items. | `batch_delete_item_metadata` | `backend/api/routes/metadata.py:1563` |
| `DELETE` | `/api/v1/metadata/items/{account_id}/{item_id}` | Remove metadata from an item. | `delete_item_metadata` | `backend/api/routes/metadata.py:1538` |
| `GET` | `/api/v1/metadata/items/{account_id}/{item_id}` | Get metadata for a specific item. | `get_item_metadata` | `backend/api/routes/metadata.py:1226` |
| `PATCH` | `/api/v1/metadata/items/{account_id}/{item_id}/ai-suggestions` | - | `update_item_ai_suggestions` | `backend/api/routes/metadata.py:1424` |
| `POST` | `/api/v1/metadata/items/{account_id}/{item_id}/ai-suggestions/accept` | - | `accept_item_ai_suggestion` | `backend/api/routes/metadata.py:1457` |
| `POST` | `/api/v1/metadata/items/{account_id}/{item_id}/ai-suggestions/reject` | - | `reject_item_ai_suggestion` | `backend/api/routes/metadata.py:1508` |
| `PATCH` | `/api/v1/metadata/items/{account_id}/{item_id}/attributes/{attribute_id}` | Update one metadata attribute value for one item. | `update_item_metadata_attribute` | `backend/api/routes/metadata.py:1241` |
| `GET` | `/api/v1/metadata/items/{account_id}/{item_id}/history` | List metadata change history for one item. | `get_item_metadata_history` | `backend/api/routes/metadata.py:1597` |
| `GET` | `/api/v1/metadata/layouts` | - | `list_metadata_form_layouts` | `backend/api/routes/metadata.py:767` |
| `GET` | `/api/v1/metadata/layouts/{category_id}` | - | `get_metadata_form_layout` | `backend/api/routes/metadata.py:780` |
| `PUT` | `/api/v1/metadata/layouts/{category_id}` | - | `upsert_metadata_form_layout` | `backend/api/routes/metadata.py:802` |
| `GET` | `/api/v1/metadata/plugins` | List metadata plugins. | `list_metadata_plugins` | `backend/api/routes/metadata.py:1762` |
| `POST` | `/api/v1/metadata/plugins/{plugin_key}/activate` | Activate a metadata plugin and ensure managed schema exists. | `activate_metadata_plugin` | `backend/api/routes/metadata.py:1770` |
| `POST` | `/api/v1/metadata/plugins/{plugin_key}/deactivate` | Deactivate a metadata plugin. | `deactivate_metadata_plugin` | `backend/api/routes/metadata.py:1793` |
| `GET` | `/api/v1/metadata/rules` | List metadata rules by priority. | `list_metadata_rules` | `backend/api/routes/metadata.py:1628` |
| `POST` | `/api/v1/metadata/rules` | Create a metadata rule. | `create_metadata_rule` | `backend/api/routes/metadata.py:1636` |
| `POST` | `/api/v1/metadata/rules/preview` | Preview how many items would be changed by a rule. | `preview_metadata_rule` | `backend/api/routes/metadata.py:1705` |
| `DELETE` | `/api/v1/metadata/rules/{rule_id}` | Delete a metadata rule. | `delete_metadata_rule` | `backend/api/routes/metadata.py:1692` |
| `PATCH` | `/api/v1/metadata/rules/{rule_id}` | Update a metadata rule. | `update_metadata_rule` | `backend/api/routes/metadata.py:1655` |
## SYSTEM

| Method | Path | Summary | Handler | Source |
|--------|------|---------|---------|--------|
| `GET` | `/health` | Health check endpoint. | `health_check` | `backend/main.py:119` |
