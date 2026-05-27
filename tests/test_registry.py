"""Smoke tests: tool registry, schemas, and uniqueness."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tg_account_mcp.server import _handler_map, _tool_defs, build_server
from tg_account_mcp import tools as t


EXPECTED_TOOLS = {
    # existing
    "tg_list_dialogs",
    "tg_read_history",
    "tg_send_message",
    "tg_edit_message",
    "tg_delete_message",
    "tg_search",
    "tg_mark_read",
    "tg_list_contacts",
    "tg_resolve_username",
    # block A — media
    "tg_send_photo",
    "tg_send_document",
    "tg_send_video",
    "tg_send_voice",
    "tg_send_audio",
    "tg_send_animation",
    "tg_send_sticker",
    "tg_send_media_group",
    "tg_download_media",
    "tg_get_media_info",
    # block B — bots
    "tg_send_to_bot",
    "tg_wait_bot_reply",
    "tg_get_bot_keyboard",
    "tg_click_inline_button",
    # block C — chats/messages
    "tg_get_chat_info",
    "tg_forward_messages",
    "tg_pin_message",
    "tg_unpin_message",
    "tg_get_pinned_messages",
    # block D — reactions/users/groups/utils
    "tg_set_reaction",
    "tg_get_message_reactions",
    "tg_get_user_info",
    "tg_download_profile_photo",
    "tg_join_chat",
    "tg_leave_chat",
    "tg_list_participants",
    "tg_typing",
    "tg_set_online_status",
    "tg_get_me",
}


def test_all_expected_tools_registered():
    names = {d.name for d in _tool_defs()}
    missing = EXPECTED_TOOLS - names
    assert not missing, f"missing tools: {missing}"


def test_no_duplicate_tool_names():
    names = [d.name for d in _tool_defs()]
    assert len(names) == len(set(names)), "duplicate tool names"


def test_every_tool_has_handler():
    handlers = _handler_map()
    for d in _tool_defs():
        assert d.name in handlers, f"{d.name} has no handler"
        assert callable(handlers[d.name]), f"{d.name} handler is not callable"


def test_every_schema_is_object():
    for d in _tool_defs():
        schema = d.inputSchema
        assert schema.get("type") == "object", f"{d.name} schema is not object"


def test_build_server_runs():
    srv = build_server()
    assert srv is not None
    assert srv.name == "tg-account-mcp"


def test_helpers_handle_missing_attrs():
    """Sanity: helpers tolerate stripped-down mocks."""
    fake = MagicMock(spec=[])
    fake.id = 7
    fake.text = "hi"
    assert t._media_kind(fake) is None
    assert t._extract_keyboard(fake) == []


@pytest.fixture
def mock_client():
    c = AsyncMock()
    c.is_connected.return_value = True
    c.get_entity = AsyncMock(return_value=MagicMock())
    return c


@pytest.mark.asyncio
async def test_send_photo_resolves_path(mock_client, tmp_path):
    f = tmp_path / "pic.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    sent = MagicMock()
    sent.id = 1
    sent.date = None
    sent.chat_id = 99
    mock_client.send_file = AsyncMock(return_value=sent)
    result = await t.tg_send_photo(mock_client, dialog_id=99, file=str(f), caption="cap")
    assert result["id"] == 1
    args, kwargs = mock_client.send_file.call_args
    assert kwargs["caption"] == "cap"
    assert kwargs["force_document"] is False


@pytest.mark.asyncio
async def test_send_photo_url_passthrough(mock_client):
    sent = MagicMock()
    sent.id = 2
    sent.date = None
    sent.chat_id = 99
    mock_client.send_file = AsyncMock(return_value=sent)
    result = await t.tg_send_photo(
        mock_client, dialog_id=99, file="https://example.com/x.png"
    )
    assert result["id"] == 2


@pytest.mark.asyncio
async def test_send_photo_missing_file_raises(mock_client):
    with pytest.raises(FileNotFoundError):
        await t.tg_send_photo(mock_client, dialog_id=99, file="/nope/missing.png")


@pytest.mark.asyncio
async def test_media_group_validates_size(mock_client):
    with pytest.raises(ValueError):
        await t.tg_send_media_group(mock_client, dialog_id=99, files=[])
    with pytest.raises(ValueError):
        await t.tg_send_media_group(
            mock_client, dialog_id=99, files=["x"] * 11
        )


@pytest.mark.asyncio
async def test_click_inline_button_requires_selector(mock_client):
    msg = MagicMock()
    msg.reply_markup = MagicMock()  # truthy
    mock_client.get_messages = AsyncMock(return_value=msg)
    with pytest.raises(ValueError):
        await t.tg_click_inline_button(mock_client, dialog_id=1, message_id=2)


@pytest.mark.asyncio
async def test_send_to_bot_rejects_me(mock_client):
    with pytest.raises(ValueError):
        await t.tg_send_to_bot(mock_client, bot="me", text="hi")


@pytest.mark.asyncio
async def test_typing_validates_action(mock_client):
    with pytest.raises(ValueError):
        await t.tg_typing(mock_client, dialog_id=1, action="dancing")
