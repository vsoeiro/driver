
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from backend.workers.handlers.sync import sync_items_handler
from backend.db.models import LinkedAccount

@pytest.mark.asyncio
async def test_sync_items_handler():
    # Setup
    account_id = uuid4()
    root_item_id = "root_id"
    folder_id = "folder_id"
    file_id = "file_id"
    
    mock_session = AsyncMock()
    mock_execute_result = MagicMock()
    mock_execute_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_execute_result
    
    # Mock Account
    mock_account = LinkedAccount(id=account_id)
    mock_session.get.return_value = mock_account
    
    # Mock provider client factory
    with patch("backend.workers.handlers.sync.build_drive_client") as mock_build_client:
        mock_client = MagicMock()
        mock_build_client.return_value = mock_client
        
        # Mock Root Item
        mock_root_item = MagicMock()
        mock_root_item.id = root_item_id
        mock_root_item.name = "Root"
        mock_root_item.item_type = "folder"
        mock_root_item.size = 0
        mock_root_item.created_at = None
        mock_root_item.modified_at = None
        mock_root_item.mime_type = None
        
        mock_client.get_item_metadata = AsyncMock(return_value=mock_root_item)
        
        # Mock List Folder Items
        mock_folder_item = MagicMock()
        mock_folder_item.id = folder_id
        mock_folder_item.name = "MyFolder"
        mock_folder_item.item_type = "folder"
        mock_folder_item.size = 0
        mock_folder_item.parent_reference = {"id": root_item_id}
        
        mock_file_item = MagicMock()
        mock_file_item.id = file_id
        mock_file_item.name = "MyFile.txt"
        mock_file_item.item_type = "file"
        mock_file_item.size = 100
        mock_file_item.parent_reference = {"id": folder_id}
        
        # 1st call: List Root -> Returns [MyFolder]
        # 2nd call: List MyFolder -> Returns [MyFile.txt]
        # 3rd call: List MyFile (not needed, loop checks type)
        
        mock_children_root = MagicMock()
        mock_children_root.items = [mock_folder_item]
        mock_children_root.next_link = None
        
        mock_children_folder = MagicMock()
        mock_children_folder.items = [mock_file_item]
        mock_children_folder.next_link = None
        
        # Mock empty list for recursion on file/empty folder?
        # The recursive logic calls list_folder_items only for folders.
        
        mock_client.list_folder_items = AsyncMock(side_effect=[
            mock_children_root,   # For root
            mock_children_folder, # For MyFolder
        ])
        
        with patch("backend.workers.handlers.sync.fetch_item_signatures_by_item_id", new_callable=AsyncMock) as mock_fetch_signatures:
            mock_fetch_signatures.return_value = {}
            with patch("backend.workers.handlers.sync.bulk_upsert_item_payloads", new_callable=AsyncMock) as mock_bulk_upsert:
                # Execute
                payload = {"account_id": str(account_id)}
                stats = await sync_items_handler(payload, mock_session)

                # Verify
                assert stats["processed"] == 3  # Root + Folder + File
                assert stats["created"] == 3
                assert stats["updated"] == 0
                assert stats["unchanged"] == 0
                assert stats["errors"] == 0

                mock_bulk_upsert.assert_awaited_once()
                call_payloads = mock_bulk_upsert.await_args.kwargs["payloads"]
                upserted_ids = {row["item_id"] for row in call_payloads}
                assert upserted_ids == {root_item_id, folder_id, file_id}
