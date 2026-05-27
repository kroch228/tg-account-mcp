from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from tg_account_mcp import tools as t
from tg_account_mcp.client import ensure_authorized, get_client

DialogId = {"oneOf": [{"type": "integer"}, {"type": "string"}]}
DialogIdNullable = {
    "oneOf": [{"type": "integer"}, {"type": "string"}, {"type": "null"}],
    "default": None,
}
ParseMode = {
    "type": "string",
    "enum": ["md", "markdown", "html"],
    "description": "Optional formatting: 'md'/'markdown' or 'html'",
}

ToolHandler = Callable[..., Awaitable[Any]]


def _tool(
    name: str,
    description: str,
    schema: dict[str, Any],
    handler: ToolHandler,
    *,
    needs_client: bool = True,
) -> tuple[Tool, ToolHandler, bool]:
    return Tool(name=name, description=description, inputSchema=schema), handler, needs_client


def _registry() -> list[tuple[Tool, ToolHandler, bool]]:
    return [
        # ── Existing ────────────────────────────────────────────────────
        _tool(
            "tg_list_dialogs",
            "List Telegram dialogs (chats, channels, users). Returns id, title, kind, unread_count, last_message_at.",
            {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50, "description": "Max dialogs to return"},
                    "archived": {"type": "boolean", "default": False, "description": "Include archived dialogs"},
                },
            },
            t.tg_list_dialogs,
        ),
        _tool(
            "tg_read_history",
            "Read message history from a dialog. dialog_id accepts numeric id, @username, or 'me' (saved messages).",
            {
                "type": "object",
                "properties": {
                    "dialog_id": {**DialogId, "description": "Peer id, @username, or 'me'"},
                    "limit": {"type": "integer", "default": 50},
                    "offset_id": {"type": "integer", "default": 0, "description": "Return messages before this message id"},
                },
                "required": ["dialog_id"],
            },
            t.tg_read_history,
        ),
        _tool(
            "tg_send_message",
            "Send a message to a dialog. Supports markdown/html parse_mode. Write action — logged to stderr.",
            {
                "type": "object",
                "properties": {
                    "dialog_id": DialogId,
                    "text": {"type": "string"},
                    "reply_to": {"type": "integer", "description": "Message id to reply to"},
                    "silent": {"type": "boolean", "default": False, "description": "Send without notification"},
                    "parse_mode": ParseMode,
                    "link_preview": {"type": "boolean", "default": True},
                },
                "required": ["dialog_id", "text"],
            },
            t.tg_send_message,
        ),
        _tool(
            "tg_edit_message",
            "Edit an existing message. Supports parse_mode.",
            {
                "type": "object",
                "properties": {
                    "dialog_id": DialogId,
                    "message_id": {"type": "integer"},
                    "text": {"type": "string"},
                    "parse_mode": ParseMode,
                    "link_preview": {"type": "boolean", "default": True},
                },
                "required": ["dialog_id", "message_id", "text"],
            },
            t.tg_edit_message,
        ),
        _tool(
            "tg_delete_message",
            "Delete messages. Write action — logged to stderr.",
            {
                "type": "object",
                "properties": {
                    "dialog_id": DialogId,
                    "message_ids": {"type": "array", "items": {"type": "integer"}},
                    "revoke": {"type": "boolean", "default": True, "description": "Delete for everyone"},
                },
                "required": ["dialog_id", "message_ids"],
            },
            t.tg_delete_message,
        ),
        _tool(
            "tg_search",
            "Search messages globally or within a specific dialog.",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "dialog_id": DialogIdNullable,
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["query"],
            },
            t.tg_search,
        ),
        _tool(
            "tg_mark_read",
            "Mark messages as read in a dialog.",
            {
                "type": "object",
                "properties": {
                    "dialog_id": DialogId,
                    "max_message_id": {"type": "integer", "description": "Mark all up to this id as read. Omit for all."},
                },
                "required": ["dialog_id"],
            },
            t.tg_mark_read,
        ),
        _tool(
            "tg_list_contacts",
            "List all contacts from the account's contact book.",
            {"type": "object", "properties": {}},
            t.tg_list_contacts,
        ),
        _tool(
            "tg_resolve_username",
            "Resolve a @username to entity id, kind, and title.",
            {
                "type": "object",
                "properties": {"username": {"type": "string", "description": "Username with or without leading @"}},
                "required": ["username"],
            },
            t.tg_resolve_username,
        ),
        # ── Block A: Media ─────────────────────────────────────────────
        _tool(
            "tg_send_photo",
            "Send a photo. `file` is an absolute path, a path relative to cwd, or an http(s) URL.",
            {
                "type": "object",
                "properties": {
                    "dialog_id": DialogId,
                    "file": {"type": "string", "description": "Absolute path, path relative to cwd, or http(s) URL"},
                    "caption": {"type": "string"},
                    "reply_to": {"type": "integer"},
                    "silent": {"type": "boolean", "default": False},
                    "parse_mode": ParseMode,
                },
                "required": ["dialog_id", "file"],
            },
            t.tg_send_photo,
        ),
        _tool(
            "tg_send_document",
            "Send a file as a document (no auto-detection). Path or URL.",
            {
                "type": "object",
                "properties": {
                    "dialog_id": DialogId,
                    "file": {"type": "string"},
                    "caption": {"type": "string"},
                    "reply_to": {"type": "integer"},
                    "silent": {"type": "boolean", "default": False},
                    "parse_mode": ParseMode,
                },
                "required": ["dialog_id", "file"],
            },
            t.tg_send_document,
        ),
        _tool(
            "tg_send_video",
            "Send a video with optional caption. Path or URL.",
            {
                "type": "object",
                "properties": {
                    "dialog_id": DialogId,
                    "file": {"type": "string"},
                    "caption": {"type": "string"},
                    "reply_to": {"type": "integer"},
                    "silent": {"type": "boolean", "default": False},
                    "supports_streaming": {"type": "boolean", "default": True},
                    "parse_mode": ParseMode,
                },
                "required": ["dialog_id", "file"],
            },
            t.tg_send_video,
        ),
        _tool(
            "tg_send_voice",
            "Send a voice note (.ogg/.opus). Path or URL.",
            {
                "type": "object",
                "properties": {
                    "dialog_id": DialogId,
                    "file": {"type": "string"},
                    "reply_to": {"type": "integer"},
                    "silent": {"type": "boolean", "default": False},
                },
                "required": ["dialog_id", "file"],
            },
            t.tg_send_voice,
        ),
        _tool(
            "tg_send_audio",
            "Send an audio file (mp3/etc). Path or URL.",
            {
                "type": "object",
                "properties": {
                    "dialog_id": DialogId,
                    "file": {"type": "string"},
                    "caption": {"type": "string"},
                    "reply_to": {"type": "integer"},
                    "silent": {"type": "boolean", "default": False},
                },
                "required": ["dialog_id", "file"],
            },
            t.tg_send_audio,
        ),
        _tool(
            "tg_send_animation",
            "Send a GIF / animation. Path or URL.",
            {
                "type": "object",
                "properties": {
                    "dialog_id": DialogId,
                    "file": {"type": "string"},
                    "caption": {"type": "string"},
                    "reply_to": {"type": "integer"},
                    "silent": {"type": "boolean", "default": False},
                },
                "required": ["dialog_id", "file"],
            },
            t.tg_send_animation,
        ),
        _tool(
            "tg_send_sticker",
            "Send a sticker (.webp/.tgs/.webm).",
            {
                "type": "object",
                "properties": {
                    "dialog_id": DialogId,
                    "file": {"type": "string"},
                    "reply_to": {"type": "integer"},
                    "silent": {"type": "boolean", "default": False},
                },
                "required": ["dialog_id", "file"],
            },
            t.tg_send_sticker,
        ),
        _tool(
            "tg_send_media_group",
            "Send an album / media group (max 10 items). `files` is a list of paths or URLs.",
            {
                "type": "object",
                "properties": {
                    "dialog_id": DialogId,
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 10,
                    },
                    "caption": {"type": "string", "description": "Caption attached to the first item"},
                    "reply_to": {"type": "integer"},
                    "silent": {"type": "boolean", "default": False},
                },
                "required": ["dialog_id", "files"],
            },
            t.tg_send_media_group,
        ),
        _tool(
            "tg_download_media",
            "Download media from a message. out_path: directory or full filename, absolute or relative to cwd. Returns saved absolute path.",
            {
                "type": "object",
                "properties": {
                    "dialog_id": DialogId,
                    "message_id": {"type": "integer"},
                    "out_path": {"type": "string", "description": "Directory or filename. Omit to use cwd."},
                },
                "required": ["dialog_id", "message_id"],
            },
            t.tg_download_media,
        ),
        _tool(
            "tg_get_media_info",
            "Inspect media on a message without downloading (mime_type, size, duration, dimensions).",
            {
                "type": "object",
                "properties": {
                    "dialog_id": DialogId,
                    "message_id": {"type": "integer"},
                },
                "required": ["dialog_id", "message_id"],
            },
            t.tg_get_media_info,
        ),
        # ── Block B: Bot interaction ───────────────────────────────────
        _tool(
            "tg_send_to_bot",
            "Send a message to a bot (numeric id or @username). Same semantics as tg_send_message but rejects 'me'.",
            {
                "type": "object",
                "properties": {
                    "bot": DialogId,
                    "text": {"type": "string"},
                    "silent": {"type": "boolean", "default": False},
                    "reply_to": {"type": "integer"},
                    "parse_mode": ParseMode,
                },
                "required": ["bot", "text"],
            },
            t.tg_send_to_bot,
        ),
        _tool(
            "tg_wait_bot_reply",
            "Wait up to `timeout` seconds for a new incoming message from a bot. Returns the message dict (with `keyboard` field) or null on timeout.",
            {
                "type": "object",
                "properties": {
                    "bot": DialogId,
                    "after_message_id": {
                        "type": "integer",
                        "description": "Ignore messages with id <= this. Omit to use the latest known message.",
                    },
                    "timeout": {"type": "number", "default": 15.0, "description": "Seconds"},
                    "poll_interval": {"type": "number", "default": 0.7},
                },
                "required": ["bot"],
            },
            t.tg_wait_bot_reply,
        ),
        _tool(
            "tg_get_bot_keyboard",
            "Return the inline keyboard attached to a message (2D list of button dicts).",
            {
                "type": "object",
                "properties": {
                    "dialog_id": DialogId,
                    "message_id": {"type": "integer"},
                },
                "required": ["dialog_id", "message_id"],
            },
            t.tg_get_bot_keyboard,
        ),
        _tool(
            "tg_click_inline_button",
            "Click an inline button on a message. Provide ONE of: text, data, or row+col.",
            {
                "type": "object",
                "properties": {
                    "dialog_id": DialogId,
                    "message_id": {"type": "integer"},
                    "text": {"type": "string", "description": "Button label to match"},
                    "data": {"type": "string", "description": "Callback data payload"},
                    "row": {"type": "integer", "description": "Row index (0-based)"},
                    "col": {"type": "integer", "description": "Column index (0-based)"},
                },
                "required": ["dialog_id", "message_id"],
            },
            t.tg_click_inline_button,
        ),
        # ── Block C: Chats / Messages extension ───────────────────────
        _tool(
            "tg_get_chat_info",
            "Detailed info about a chat, channel, or user.",
            {
                "type": "object",
                "properties": {"dialog_id": DialogId},
                "required": ["dialog_id"],
            },
            t.tg_get_chat_info,
        ),
        _tool(
            "tg_forward_messages",
            "Forward messages from one dialog to another.",
            {
                "type": "object",
                "properties": {
                    "from_dialog": DialogId,
                    "to_dialog": DialogId,
                    "message_ids": {"type": "array", "items": {"type": "integer"}},
                    "silent": {"type": "boolean", "default": False},
                    "drop_author": {"type": "boolean", "default": False},
                },
                "required": ["from_dialog", "to_dialog", "message_ids"],
            },
            t.tg_forward_messages,
        ),
        _tool(
            "tg_pin_message",
            "Pin a message in a dialog.",
            {
                "type": "object",
                "properties": {
                    "dialog_id": DialogId,
                    "message_id": {"type": "integer"},
                    "notify": {"type": "boolean", "default": False},
                    "pm_oneside": {"type": "boolean", "default": False, "description": "Pin only on your side in PMs"},
                },
                "required": ["dialog_id", "message_id"],
            },
            t.tg_pin_message,
        ),
        _tool(
            "tg_unpin_message",
            "Unpin a specific message, or all pinned messages when message_id is omitted.",
            {
                "type": "object",
                "properties": {
                    "dialog_id": DialogId,
                    "message_id": {"type": "integer"},
                },
                "required": ["dialog_id"],
            },
            t.tg_unpin_message,
        ),
        _tool(
            "tg_get_pinned_messages",
            "Return pinned messages in a dialog.",
            {
                "type": "object",
                "properties": {
                    "dialog_id": DialogId,
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["dialog_id"],
            },
            t.tg_get_pinned_messages,
        ),
        # ── Block D: Reactions / Users / Groups / Utils ────────────────
        _tool(
            "tg_set_reaction",
            "Set or clear a reaction on a message. Pass empty emoji to remove.",
            {
                "type": "object",
                "properties": {
                    "dialog_id": DialogId,
                    "message_id": {"type": "integer"},
                    "emoji": {
                        "type": ["string", "null"],
                        "description": "Single emoji like '👍'. Null/empty removes the reaction.",
                    },
                    "big": {"type": "boolean", "default": False, "description": "Big reaction animation"},
                },
                "required": ["dialog_id", "message_id"],
            },
            t.tg_set_reaction,
        ),
        _tool(
            "tg_get_message_reactions",
            "Return reaction counts per message.",
            {
                "type": "object",
                "properties": {
                    "dialog_id": DialogId,
                    "message_ids": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["dialog_id", "message_ids"],
            },
            t.tg_get_message_reactions,
        ),
        _tool(
            "tg_get_user_info",
            "Detailed user info. `user` is a numeric id, @username, or 'me'.",
            {
                "type": "object",
                "properties": {"user": DialogId},
                "required": ["user"],
            },
            t.tg_get_user_info,
        ),
        _tool(
            "tg_download_profile_photo",
            "Download a user's profile photo. Returns saved absolute path or null if no photo.",
            {
                "type": "object",
                "properties": {
                    "user": DialogId,
                    "out_path": {"type": "string", "description": "Directory or filename. Omit to use cwd."},
                },
                "required": ["user"],
            },
            t.tg_download_profile_photo,
        ),
        _tool(
            "tg_join_chat",
            "Join a chat by @username, channel id, or t.me/+invite link.",
            {
                "type": "object",
                "properties": {
                    "chat": {
                        "oneOf": [{"type": "integer"}, {"type": "string"}],
                        "description": "@username, numeric id, or t.me/+invite link / +invite_hash",
                    },
                },
                "required": ["chat"],
            },
            t.tg_join_chat,
        ),
        _tool(
            "tg_leave_chat",
            "Leave a channel or supergroup.",
            {
                "type": "object",
                "properties": {"chat": DialogId},
                "required": ["chat"],
            },
            t.tg_leave_chat,
        ),
        _tool(
            "tg_list_participants",
            "List participants of a channel/supergroup. `search` filters by username/name.",
            {
                "type": "object",
                "properties": {
                    "chat": DialogId,
                    "limit": {"type": "integer", "default": 100},
                    "search": {"type": "string", "default": ""},
                },
                "required": ["chat"],
            },
            t.tg_list_participants,
        ),
        _tool(
            "tg_typing",
            "Send a typing / upload / record action. Useful before send_message to look more human.",
            {
                "type": "object",
                "properties": {
                    "dialog_id": DialogId,
                    "action": {
                        "type": "string",
                        "enum": [
                            "typing",
                            "upload_photo",
                            "upload_document",
                            "record_voice",
                            "record_video",
                            "cancel",
                        ],
                        "default": "typing",
                    },
                    "cancel": {"type": "boolean", "default": False},
                },
                "required": ["dialog_id"],
            },
            t.tg_typing,
        ),
        _tool(
            "tg_set_online_status",
            "Set the account's online presence. offline=true hides last-seen activity.",
            {
                "type": "object",
                "properties": {
                    "online": {"type": "boolean", "default": True},
                },
            },
            t.tg_set_online_status,
        ),
        _tool(
            "tg_get_me",
            "Return the authorized user's identity (id, name, username, phone, premium).",
            {"type": "object", "properties": {}},
            t.tg_get_me,
        ),
    ]


def _tool_defs() -> list[Tool]:
    return [t_def for t_def, _, _ in _registry()]


def _handler_map() -> dict[str, ToolHandler]:
    return {t_def.name: handler for t_def, handler, _ in _registry()}


_client = None


async def _get_connected_client():
    global _client
    if _client is None:
        _client = get_client()
    if not _client.is_connected():
        await _client.connect()
    await ensure_authorized(_client)
    return _client


async def _handle_call(name: str, arguments: dict[str, Any]) -> Any:
    handlers = _handler_map()
    handler = handlers.get(name)
    if handler is None:
        raise ValueError(f"Unknown tool: {name}")
    client = await _get_connected_client()
    return await handler(client, **arguments)


def build_server() -> Server:
    server = Server("tg-account-mcp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return _tool_defs()

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        try:
            result = await _handle_call(name, arguments)
            return [
                TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))
            ]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e), "type": type(e).__name__}))]

    return server


async def _run() -> None:
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
