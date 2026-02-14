
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
    
    # Mock Account
    mock_account = LinkedAccount(id=account_id, token="token")
    mock_session.get.return_value = mock_account
    
    # Mock GraphClient
    with patch("backend.workers.handlers.sync.GraphClient") as MockGraphClient:
        mock_client = MockGraphClient.return_value
        
        # Mock Root Item
        mock_root_item = MagicMock()
        mock_root_item.id = root_item_id
        mock_root_item.name = "Root"
        mock_root_item.item_type = "folder"
        mock_root_item.size = 0
        mock_root_item.created_at = None
        mock_root_item.modified_at = None
        mock_root_item.mime_type = None
        
        mock_client.get_item_metadata.return_value = mock_root_item
        
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
        
        mock_client.list_folder_items.side_effect = [
            mock_children_root,   # For root
            mock_children_folder, # For MyFolder
        ]
        
        # Mock upsert_item_record
        with patch("backend.workers.handlers.sync.upsert_item_record", new_callable=AsyncMock) as mock_upsert:
            
            # Execute
            payload = {"account_id": str(account_id)}
            stats = await sync_items_handler(payload, mock_session)
            
            # Verify
            assert stats["processed"] == 3 # Root + Folder + File
            assert stats["errors"] == 0
            
            # Check upsert calls
            assert mock_upsert.call_count == 3
            
            # 1. Root
            mock_upsert.assert_any_call(mock_session, mock_account, mock_root_item, parent_id=None, path="/")
            
            # 2. Folder
            mock_upsert.assert_any_call(mock_session, mock_account, mock_folder_item, parent_id=root_item_id, path="/MyFolder")
            
            # 3. File
            mock_upsert.assert_any_call(mock_session, mock_account, mock_file_item, parent_id=folder_id, path="/MyFolder/MyFile.txt")
