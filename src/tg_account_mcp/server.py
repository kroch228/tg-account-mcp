from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from tg_account_mcp.client import get_client, ensure_authorized
from tg_account_mcp import tools as t


def _tool_defs() -> list[Tool]:
    return [
        Tool(
            name="tg_list_dialogs",
            description="List Telegram dialogs (chats, channels, users). Returns id, title, kind, unread_count, last_message_at.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "default": 50,
                        "description": "Max dialogs to return",
                    },
                    "archived": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include archived dialogs",
                    },
                },
            },
        ),
        Tool(
            name="tg_read_history",
            description="Read message history from a dialog. dialog_id accepts numeric id, @username, or 'me' (saved messages).",
            inputSchema={
                "type": "object",
                "properties": {
                    "dialog_id": {
                        "oneOf": [{"type": "integer"}, {"type": "string"}],
                        "description": "Peer id, @username, or 'me'",
                    },
                    "limit": {"type": "integer", "default": 50},
                    "offset_id": {
                        "type": "integer",
                        "default": 0,
                        "description": "Return messages before this message id",
                    },
                },
                "required": ["dialog_id"],
            },
        ),
        Tool(
            name="tg_send_message",
            description="Send a message to a dialog. Write action — logged to stderr.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dialog_id": {"oneOf": [{"type": "integer"}, {"type": "string"}]},
                    "text": {"type": "string"},
                    "reply_to": {"type": "integer", "description": "Message id to reply to"},
                    "silent": {
                        "type": "boolean",
                        "default": False,
                        "description": "Send without notification",
                    },
                },
                "required": ["dialog_id", "text"],
            },
        ),
        Tool(
            name="tg_edit_message",
            description="Edit an existing message.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dialog_id": {"oneOf": [{"type": "integer"}, {"type": "string"}]},
                    "message_id": {"type": "integer"},
                    "text": {"type": "string"},
                },
                "required": ["dialog_id", "message_id", "text"],
            },
        ),
        Tool(
            name="tg_delete_message",
            description="Delete messages. Write action — logged to stderr.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dialog_id": {"oneOf": [{"type": "integer"}, {"type": "string"}]},
                    "message_ids": {"type": "array", "items": {"type": "integer"}},
                    "revoke": {
                        "type": "boolean",
                        "default": True,
                        "description": "Delete for everyone",
                    },
                },
                "required": ["dialog_id", "message_ids"],
            },
        ),
        Tool(
            name="tg_search",
            description="Search messages globally or within a specific dialog.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "dialog_id": {
                        "oneOf": [{"type": "integer"}, {"type": "string"}, {"type": "null"}],
                        "default": None,
                    },
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="tg_mark_read",
            description="Mark messages as read in a dialog.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dialog_id": {"oneOf": [{"type": "integer"}, {"type": "string"}]},
                    "max_message_id": {
                        "type": "integer",
                        "description": "Mark all up to this id as read. Omit for all.",
                    },
                },
                "required": ["dialog_id"],
            },
        ),
        Tool(
            name="tg_list_contacts",
            description="List all contacts from the account's contact book.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="tg_resolve_username",
            description="Resolve a @username to entity id, kind, and title.",
            inputSchema={
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "Username without @"},
                },
                "required": ["username"],
            },
        ),
    ]


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
    client = await _get_connected_client()

    match name:
        case "tg_list_dialogs":
            return await t.tg_list_dialogs(client, **arguments)
        case "tg_read_history":
            return await t.tg_read_history(client, **arguments)
        case "tg_send_message":
            return await t.tg_send_message(client, **arguments)
        case "tg_edit_message":
            return await t.tg_edit_message(client, **arguments)
        case "tg_delete_message":
            return await t.tg_delete_message(client, **arguments)
        case "tg_search":
            return await t.tg_search(client, **arguments)
        case "tg_mark_read":
            return await t.tg_mark_read(client, **arguments)
        case "tg_list_contacts":
            return await t.tg_list_contacts(client)
        case "tg_resolve_username":
            return await t.tg_resolve_username(client, **arguments)
        case _:
            raise ValueError(f"Unknown tool: {name}")


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
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    return server


async def _run() -> None:
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
