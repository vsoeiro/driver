from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from backend.application.metadata.rules_service import MetadataRulesService


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
