from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from backend.api.routes import ai as ai_routes


@pytest.mark.asyncio
async def test_ai_routes_delegate_to_service(monkeypatch):
    session_id = uuid4()
    confirmation_id = uuid4()
    message_response = SimpleNamespace(id=uuid4())
    service = SimpleNamespace(
        create_session=AsyncMock(return_value="created"),
        list_sessions=AsyncMock(return_value=["listed"]),
        delete_session=AsyncMock(return_value=None),
        generate_session_title=AsyncMock(return_value="titled"),
        get_messages=AsyncMock(return_value=[message_response]),
        post_message=AsyncMock(return_value="posted"),
        resolve_confirmation=AsyncMock(return_value="confirmed"),
        tools_catalog=AsyncMock(return_value="catalog"),
    )
    monkeypatch.setattr(ai_routes, "AIChatService", lambda db: service)

    assert await ai_routes.create_chat_session(SimpleNamespace(title="AI"), db=object()) == "created"
    assert await ai_routes.list_chat_sessions(db=object(), limit=10, offset=2) == ["listed"]
    assert await ai_routes.delete_chat_session(session_id, db=object()) is None
    assert await ai_routes.generate_chat_session_title(session_id, db=object()) == "titled"
    assert await ai_routes.get_chat_messages(session_id, db=object(), limit=50) == [message_response]
    assert await ai_routes.post_chat_message(session_id, SimpleNamespace(message="hello"), db=object()) == "posted"
    assert (
        await ai_routes.resolve_chat_confirmation(
            session_id,
            confirmation_id,
            SimpleNamespace(approve=True),
            db=object(),
        )
        == "confirmed"
    )
    assert await ai_routes.get_tools_catalog(db=object()) == "catalog"

    service.create_session.assert_awaited_once_with(title="AI")
    service.list_sessions.assert_awaited_once_with(limit=10, offset=2)
    service.delete_session.assert_awaited_once_with(session_id)
    service.generate_session_title.assert_awaited_once_with(session_id)
    service.get_messages.assert_awaited_once_with(session_id, limit=50)
    service.post_message.assert_awaited_once_with(session_id, message="hello")
    service.resolve_confirmation.assert_awaited_once_with(
        session_id=session_id,
        confirmation_id=confirmation_id,
        approve=True,
    )
    service.tools_catalog.assert_awaited_once_with()
