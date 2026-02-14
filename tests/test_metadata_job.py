
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from backend.workers.handlers.metadata import update_metadata_handler
from backend.db.models import LinkedAccount, MetadataCategory, MetadataAttribute, ItemMetadata

class TestMetadataJob(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.session = AsyncMock()
        self.account_id = uuid4()
        self.category_id = uuid4()
        self.root_item_id = "root_folder"
        
        # Mock Account
        self.account = LinkedAccount(id=self.account_id)
        
        # Mock Category
        self.category = MetadataCategory(id=self.category_id, name="Comic Info")
        
        # Mock Attributes
        self.attr_id = uuid4()
        self.attributes = [
            MetadataAttribute(id=self.attr_id, name="Series", category_id=self.category_id)
        ]
        
        # Setup session.execute return values for category and attributes
        # usage: session.execute(stmt) -> result
        # result.scalar_one_or_none() -> category
        # result.scalars().all() -> attributes
        
        # We need to mock the sequence of calls to session.execute
        # 1. Select Category
        # 2. Select Attributes
        # 3. Select ItemMetadata (for each item)
        
        # Since call order matters and arguments are complex SQL statements, 
        # it's easier to mock the side effects if we assume the logic is correct 
        # or use specific side_effects based on the query string representation if possible.
        # But here, let's just use a side_effect function.

        self.mock_category_result = MagicMock()
        self.mock_category_result.scalar_one_or_none.return_value = self.category
        
        self.mock_attributes_result = MagicMock()
        self.mock_attributes_result.scalars.return_value.all.return_value = self.attributes

        self.mock_metadata_result_empty = MagicMock()
        self.mock_metadata_result_empty.scalar_one_or_none.return_value = None

        # Determine which result to return
        # simple approach: assume happy path where everything is found except ItemMetadata (so we test creation)
        
        # For simplicity in this mock, we can just return the category first, then attributes, then repeated None for ItemMetadata
        self.session.execute.side_effect = [
            self.mock_category_result,
            self.mock_attributes_result,
            self.mock_metadata_result_empty, # For root item (if file) or recursive items
            self.mock_metadata_result_empty, 
            self.mock_metadata_result_empty
        ]

        self.session.get.return_value = self.account

    @patch("backend.workers.handlers.metadata.GraphClient")
    async def test_recursive_update(self, MockGraphClient):
        # Setup Graph Client Mock
        client_instance = MockGraphClient.return_value
        
        # Root item is a folder
        root_metadata = MagicMock()
        root_metadata.item_type = "folder"
        root_metadata.id = self.root_item_id
        client_instance.get_item_metadata = AsyncMock(return_value=root_metadata)
        
        # List folder items (1 file, 1 subfolder)
        file_item = MagicMock()
        file_item.id = "file_1"
        file_item.item_type = "file"
        
        subfolder_item = MagicMock()
        subfolder_item.id = "subfolder_1"
        subfolder_item.item_type = "folder"
        
        # Subfolder contents (1 file)
        subfile_item = MagicMock()
        subfile_item.id = "file_2"
        subfile_item.item_type = "file"
        
        # Setup list_folder_items responses
        # Call 1 (root): returns [file_1, subfolder_1]
        response_1 = MagicMock()
        response_1.items = [file_item, subfolder_item]
        response_1.next_link = None
        
        # Call 2 (subfolder): returns [subfile_item]
        response_2 = MagicMock()
        response_2.items = [subfile_item]
        response_2.next_link = None
        
        client_instance.list_folder_items = AsyncMock(side_effect=[response_1, response_2])
        
        # Payload
        payload = {
            "account_id": str(self.account_id),
            "root_item_id": self.root_item_id,
            "metadata": {"Series": "New Series"},
            "category_name": "Comic Info"
        }
        
        # Execution
        stats = await update_metadata_handler(payload, self.session)
        
        # Verification
        self.assertEqual(stats["processed"], 2) # 2 files processed
        self.assertEqual(stats["updated"], 2)
        
        # Verify calls to session.add (ItemMetadata creation)
        # Should be called twice (for file_1 and file_2)
        # Note: session.add is not async
        self.assertEqual(self.session.add.call_count, 2)
        
        # Verify args passed to session.add
        calls = self.session.add.call_args_list
        
        # Check first call
        arg1 = calls[0][0][0]
        self.assertIsInstance(arg1, ItemMetadata)
        self.assertEqual(arg1.item_id, "file_1")
        self.assertEqual(arg1.values, {str(self.attr_id): "New Series"})
        
        # Check second call (might be subfile)
        arg2 = calls[1][0][0]
        self.assertIsInstance(arg2, ItemMetadata)
        self.assertEqual(arg2.item_id, "file_2")
        self.assertEqual(arg2.values, {str(self.attr_id): "New Series"})

if __name__ == "__main__":
    unittest.main()
