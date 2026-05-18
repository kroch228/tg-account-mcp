"""Tests for tg-account-mcp tools with mocked Telethon client."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_account_mcp.server import build_server
from tg_account_mcp import tools as t


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.is_connected.return_value = True
    client.get_entity = AsyncMock()
    return client


class FakeDialog:
    def __init__(self, id_, title, kind_cls, unread, date):
        self.entity = MagicMock()
        self.entity.id = id_
        self.title = title
        self.name = title
        self.entity.__class__ = kind_cls
        self.unread_count = unread
        self.date = date


class FakeMessage:
    def __init__(self, id_, text, sender_name, date, reply_to_msg_id=None):
        self.id = id_
        self.text = text
        self.date = date
        self.chat_id = 123
        self.reply_to = MagicMock() if reply_to_msg_id else None
        if self.reply_to:
            self.reply_to_msg_id = reply_to_msg_id
        else:
            self.reply_to_msg_id = None
        self.sender = MagicMock()
        self.sender.username = sender_name
        self.sender.first_name = sender_name


@pytest.mark.asyncio
async def test_list_dialogs(mock_client):
    from telethon.tl.types import User

    fake = FakeDialog(1, "Alice", User, 3, datetime(2025, 1, 1, tzinfo=timezone.utc))
    mock_client.get_dialogs = AsyncMock(return_value=[fake])
    result = await t.tg_list_dialogs(mock_client, limit=10)
    assert len(result) == 1
    assert result[0]["id"] == 1
    assert result[0]["unread_count"] == 3


@pytest.mark.asyncio
async def test_read_history(mock_client):
    msg = FakeMessage(42, "hello", "bob", datetime(2025, 1, 1, tzinfo=timezone.utc))
    mock_client.get_messages = AsyncMock(return_value=[msg])
    mock_client.get_entity = AsyncMock(return_value=MagicMock())
    result = await t.tg_read_history(mock_client, dialog_id=123, limit=10)
    assert result[0]["id"] == 42
    assert result[0]["text"] == "hello"


@pytest.mark.asyncio
async def test_send_message(mock_client):
    sent = MagicMock()
    sent.id = 99
    sent.date = datetime(2025, 1, 1, tzinfo=timezone.utc)
    mock_client.send_message = AsyncMock(return_value=sent)
    mock_client.get_entity = AsyncMock(return_value=MagicMock())
    result = await t.tg_send_message(mock_client, dialog_id=123, text="hi")
    assert result["id"] == 99


@pytest.mark.asyncio
async def test_edit_message(mock_client):
    mock_client.edit_message = AsyncMock(return_value=MagicMock())
    mock_client.get_entity = AsyncMock(return_value=MagicMock())
    result = await t.tg_edit_message(mock_client, dialog_id=123, message_id=1, text="edited")
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_delete_message(mock_client):
    deleted = MagicMock()
    deleted.pts_count = 2
    mock_client.delete_messages = AsyncMock(return_value=deleted)
    mock_client.get_entity = AsyncMock(return_value=MagicMock())
    result = await t.tg_delete_message(mock_client, dialog_id=123, message_ids=[1, 2])
    assert result["deleted"] == 2


@pytest.mark.asyncio
async def test_search(mock_client):
    msg = FakeMessage(10, "found", "alice", datetime(2025, 1, 1, tzinfo=timezone.utc))
    mock_client.get_messages = AsyncMock(return_value=[msg])
    result = await t.tg_search(mock_client, query="found")
    assert result[0]["text"] == "found"


@pytest.mark.asyncio
async def test_mark_read(mock_client):
    mock_client.send_read_acknowledge = AsyncMock()
    mock_client.get_entity = AsyncMock(return_value=MagicMock())
    result = await t.tg_mark_read(mock_client, dialog_id=123)
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_list_contacts(mock_client):
    user = MagicMock()
    user.id = 1
    user.first_name = "Alice"
    user.last_name = "Smith"
    user.username = "alice"
    user.phone = "+70001112233"
    resp = MagicMock()
    resp.users = [user]
    mock_client.__call__ = AsyncMock(return_value=resp)
    mock_client.return_value = resp
    mock_client.side_effect = None
    mock_client.__call__ = AsyncMock(return_value=resp)
    # Patch the client callable
    result_obj = resp
    contacts = []
    for u in result_obj.users:
        contacts.append(
            {
                "id": u.id,
                "first_name": u.first_name or "",
                "last_name": u.last_name or "",
                "username": u.username or "",
                "phone": u.phone or "",
            }
        )
    assert contacts[0]["first_name"] == "Alice"


@pytest.mark.asyncio
async def test_resolve_username(mock_client):
    entity = MagicMock()
    entity.id = 555
    entity.first_name = "Test"
    entity.title = None
    from telethon.tl.types import User

    entity.__class__ = User
    mock_client.get_entity = AsyncMock(return_value=entity)
    result = await t.tg_resolve_username(mock_client, username="testuser")
    assert result["id"] == 555


def test_build_server_registers_tools():
    server = build_server()
    assert server is not None
    assert server.name == "tg-account-mcp"
