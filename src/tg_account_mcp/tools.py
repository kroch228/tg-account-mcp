from __future__ import annotations

import asyncio
import sys
import time
from datetime import datetime, timezone

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.functions.contacts import GetContactsRequest
from telethon.tl.types import User, Chat, Channel

from tg_account_mcp.client import resolve_peer

_last_send: dict[str, float] = {}
SEND_COOLDOWN = 1.0


def _mask_peer(peer_key: str) -> str:
    if peer_key.startswith("+") and len(peer_key) > 6:
        return peer_key[:3] + "***" + peer_key[-4:]
    return peer_key


def _ts(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _peer_kind(entity) -> str:
    if isinstance(entity, User):
        return "user"
    if isinstance(entity, Channel):
        return "channel" if entity.broadcast else "group"
    if isinstance(entity, Chat):
        return "group"
    return "unknown"


async def _rate_limit(peer_key: str) -> None:
    now = time.time()
    last = _last_send.get(peer_key, 0)
    wait = SEND_COOLDOWN - (now - last)
    if wait > 0:
        await asyncio.sleep(wait)
    _last_send[peer_key] = time.time()


async def _with_flood_retry(coro):
    try:
        return await coro
    except FloodWaitError as e:
        if e.seconds > 60:
            raise
        await asyncio.sleep(e.seconds)
        return await coro


async def tg_list_dialogs(client: TelegramClient, limit: int = 50, archived: bool = False) -> list:
    dialogs = await client.get_dialogs(limit=limit, archived=archived)
    result = []
    for d in dialogs:
        result.append(
            {
                "id": d.entity.id,
                "title": d.title or d.name,
                "kind": _peer_kind(d.entity),
                "unread_count": d.unread_count,
                "last_message_at": _ts(d.date),
            }
        )
    return result


async def tg_read_history(
    client: TelegramClient, dialog_id: int | str, limit: int = 50, offset_id: int = 0
) -> list:
    peer = await resolve_peer(client, dialog_id)
    messages = await client.get_messages(peer, limit=limit, offset_id=offset_id)
    result = []
    for m in messages:
        sender = None
        if m.sender:
            sender = getattr(m.sender, "username", None) or getattr(m.sender, "first_name", None)
        result.append(
            {
                "id": m.id,
                "from": sender,
                "text": m.text or "",
                "date": _ts(m.date),
                "reply_to_id": m.reply_to_msg_id if m.reply_to else None,
            }
        )
    return result


async def tg_send_message(
    client: TelegramClient,
    dialog_id: int | str,
    text: str,
    reply_to: int | None = None,
    silent: bool = False,
) -> dict:
    peer = await resolve_peer(client, dialog_id)
    peer_key = str(dialog_id)
    await _rate_limit(peer_key)
    print(f"[send] peer={_mask_peer(peer_key)} text={text[:40]}...", file=sys.stderr)
    msg = await _with_flood_retry(client.send_message(peer, text, reply_to=reply_to, silent=silent))
    return {"id": msg.id, "date": _ts(msg.date)}


async def tg_edit_message(
    client: TelegramClient, dialog_id: int | str, message_id: int, text: str
) -> dict:
    peer = await resolve_peer(client, dialog_id)
    await _with_flood_retry(client.edit_message(peer, message_id, text))
    return {"ok": True}


async def tg_delete_message(
    client: TelegramClient, dialog_id: int | str, message_ids: list[int], revoke: bool = True
) -> dict:
    peer = await resolve_peer(client, dialog_id)
    peer_key = str(dialog_id)
    print(f"[delete] peer={_mask_peer(peer_key)} ids={message_ids}", file=sys.stderr)
    deleted = await _with_flood_retry(client.delete_messages(peer, message_ids, revoke=revoke))
    count = getattr(deleted, "pts_count", len(message_ids))
    return {"deleted": count}


async def tg_search(
    client: TelegramClient, query: str, dialog_id: int | str | None = None, limit: int = 20
) -> list:
    peer = await resolve_peer(client, dialog_id) if dialog_id else None
    messages = await client.get_messages(peer, search=query, limit=limit)
    result = []
    for m in messages:
        sender = None
        if m.sender:
            sender = getattr(m.sender, "username", None) or getattr(m.sender, "first_name", None)
        result.append(
            {
                "id": m.id,
                "from": sender,
                "text": m.text or "",
                "date": _ts(m.date),
                "chat_id": m.chat_id,
            }
        )
    return result


async def tg_mark_read(
    client: TelegramClient, dialog_id: int | str, max_message_id: int | None = None
) -> dict:
    peer = await resolve_peer(client, dialog_id)
    await client.send_read_acknowledge(peer, max_id=max_message_id)
    return {"ok": True}


async def tg_list_contacts(client: TelegramClient) -> list:
    result_obj = await client(GetContactsRequest(hash=0))
    contacts = []
    for user in result_obj.users:
        contacts.append(
            {
                "id": user.id,
                "first_name": user.first_name or "",
                "last_name": user.last_name or "",
                "username": user.username or "",
                "phone": user.phone or "",
            }
        )
    return contacts


async def tg_resolve_username(client: TelegramClient, username: str) -> dict:
    entity = await client.get_entity(username)
    title = getattr(entity, "title", None) or getattr(entity, "first_name", "") or ""
    return {
        "id": entity.id,
        "kind": _peer_kind(entity),
        "title": title,
    }
