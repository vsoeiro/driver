from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.application.metadata.rules_service import MetadataRulesService
from backend.schemas.metadata import MetadataRuleCreate


@pytest.mark.asyncio
async def test_validate_rule_configuration_rejects_conflicting_metadata_actions():
    service = MetadataRulesService(AsyncMock())
    with pytest.raises(HTTPException) as exc:
        await service.validate_rule_configuration(
            {
                "apply_metadata": True,
                "apply_remove_metadata": True,
                "apply_rename": False,
                "apply_move": False,
            }
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_validate_rule_configuration_requires_at_least_one_action():
    service = MetadataRulesService(AsyncMock())
    with pytest.raises(HTTPException) as exc:
        await service.validate_rule_configuration(
            {
                "apply_metadata": False,
                "apply_remove_metadata": False,
                "apply_rename": False,
                "apply_move": False,
            }
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_rule_preserves_uuid_fields_for_database_model():
    session = AsyncMock()
    session.add = Mock()
    category_id = uuid4()
    account_id = uuid4()
    session.get.return_value = SimpleNamespace(id=category_id)
    created_rule = SimpleNamespace(id=uuid4(), name="Rule UUID")
    session.refresh.side_effect = lambda rule: rule.__dict__.update(created_rule.__dict__)

    service = MetadataRulesService(session)
    payload = MetadataRuleCreate(
        name="Rule UUID",
        description="Checks UUID handling",
        account_id=account_id,
        is_active=True,
        priority=10,
        path_contains="docs",
        path_prefix=None,
        target_category_id=category_id,
        target_values={},
        apply_metadata=True,
        apply_rename=False,
        rename_template=None,
        apply_move=False,
        destination_account_id=None,
        destination_folder_id="root",
        destination_path_template=None,
        metadata_filters=[],
        include_folders=False,
    )

    result = await service.create_rule(payload)

    added_rule = session.add.call_args.args[0]
    assert added_rule.account_id == account_id
    assert added_rule.target_category_id == category_id
    assert result.id == created_rule.id
