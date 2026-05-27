from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.custom import Message
from telethon.tl.functions.account import UpdateStatusRequest
from telethon.tl.functions.channels import (
    JoinChannelRequest,
    LeaveChannelRequest,
)
from telethon.tl.functions.contacts import GetContactsRequest
from telethon.tl.functions.messages import (
    ImportChatInviteRequest,
    SendReactionRequest,
    SetTypingRequest,
    UpdatePinnedMessageRequest,
)
from telethon.tl.types import (
    Channel,
    ChannelParticipantsRecent,
    ChannelParticipantsSearch,
    Chat,
    InputMessagesFilterPinned,
    KeyboardButtonCallback,
    KeyboardButtonSwitchInline,
    KeyboardButtonUrl,
    ReactionEmoji,
    ReplyInlineMarkup,
    SendMessageCancelAction,
    SendMessageRecordAudioAction,
    SendMessageRecordVideoAction,
    SendMessageTypingAction,
    SendMessageUploadDocumentAction,
    SendMessageUploadPhotoAction,
    User,
)

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


def _peer_kind(entity: Any) -> str:
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


def _resolve_file_path(path: str) -> str:
    """Return absolute path. Accepts absolute paths or paths relative to cwd."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    return str(p)


def _looks_like_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def _resolve_file_or_url(path_or_url: str) -> str:
    """Pass through URLs, resolve local paths to absolute existing paths."""
    if _looks_like_url(path_or_url):
        return path_or_url
    return _resolve_file_path(path_or_url)


def _button_to_dict(button: Any, row_idx: int, col_idx: int) -> dict[str, Any]:
    out: dict[str, Any] = {
        "row": row_idx,
        "col": col_idx,
        "text": getattr(button, "text", "") or "",
        "kind": type(button).__name__,
    }
    if isinstance(button, KeyboardButtonCallback):
        out["data"] = button.data.decode("utf-8", errors="replace") if button.data else ""
    elif isinstance(button, KeyboardButtonUrl):
        out["url"] = button.url
    elif isinstance(button, KeyboardButtonSwitchInline):
        out["query"] = button.query
        out["same_peer"] = bool(button.same_peer)
    return out


def _extract_keyboard(message: Message) -> list[list[dict[str, Any]]]:
    markup = getattr(message, "reply_markup", None)
    if not markup or not isinstance(markup, ReplyInlineMarkup):
        return []
    rows: list[list[dict[str, Any]]] = []
    for r_idx, row in enumerate(markup.rows or []):
        out_row: list[dict[str, Any]] = []
        for c_idx, btn in enumerate(row.buttons or []):
            out_row.append(_button_to_dict(btn, r_idx, c_idx))
        rows.append(out_row)
    return rows


def _media_kind(message: Message) -> str | None:
    media = getattr(message, "media", None)
    if not media:
        return None
    cls = type(media).__name__
    if "Photo" in cls:
        return "photo"
    if "Document" in cls:
        doc = getattr(message, "document", None)
        if doc:
            for attr in getattr(doc, "attributes", None) or []:
                a_cls = type(attr).__name__
                if "Sticker" in a_cls:
                    return "sticker"
                if "Animated" in a_cls:
                    return "animation"
                if "Video" in a_cls:
                    return "video"
                if "Audio" in a_cls:
                    return "voice" if getattr(attr, "voice", False) else "audio"
        return "document"
    if "WebPage" in cls:
        return "webpage"
    if "Geo" in cls:
        return "geo"
    if "Contact" in cls:
        return "contact"
    if "Poll" in cls:
        return "poll"
    return cls.lower()


def _sender_name(message: Message) -> str | None:
    if not message.sender:
        return None
    return getattr(message.sender, "username", None) or getattr(
        message.sender, "first_name", None
    )


def _message_to_dict(message: Message) -> dict[str, Any]:
    reply_to_id = None
    if getattr(message, "reply_to", None):
        reply_to_id = getattr(message, "reply_to_msg_id", None)
    return {
        "id": message.id,
        "from": _sender_name(message),
        "text": getattr(message, "text", "") or "",
        "date": _ts(getattr(message, "date", None)),
        "chat_id": getattr(message, "chat_id", None),
        "reply_to_id": reply_to_id,
        "media_kind": _media_kind(message),
        "has_buttons": bool(
            getattr(message, "reply_markup", None)
            and isinstance(message.reply_markup, ReplyInlineMarkup)
        ),
        "out": bool(getattr(message, "out", False)),
    }


# ============================================================================
# Existing tools
# ============================================================================


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
    return [_message_to_dict(m) for m in messages]


async def tg_send_message(
    client: TelegramClient,
    dialog_id: int | str,
    text: str,
    reply_to: int | None = None,
    silent: bool = False,
    parse_mode: str | None = None,
    link_preview: bool = True,
) -> dict:
    """Send a text message.

    parse_mode: None | 'md' | 'markdown' | 'html'.
    """
    peer = await resolve_peer(client, dialog_id)
    peer_key = str(dialog_id)
    await _rate_limit(peer_key)
    print(f"[send] peer={_mask_peer(peer_key)} text={text[:40]}...", file=sys.stderr)
    msg = await _with_flood_retry(
        client.send_message(
            peer,
            text,
            reply_to=reply_to,
            silent=silent,
            parse_mode=parse_mode,
            link_preview=link_preview,
        )
    )
    return {"id": msg.id, "date": _ts(msg.date), "chat_id": msg.chat_id}


async def tg_edit_message(
    client: TelegramClient,
    dialog_id: int | str,
    message_id: int,
    text: str,
    parse_mode: str | None = None,
    link_preview: bool = True,
) -> dict:
    peer = await resolve_peer(client, dialog_id)
    await _with_flood_retry(
        client.edit_message(
            peer, message_id, text, parse_mode=parse_mode, link_preview=link_preview
        )
    )
    return {"ok": True}


async def tg_delete_message(
    client: TelegramClient, dialog_id: int | str, message_ids: list[int], revoke: bool = True
) -> dict:
    peer = await resolve_peer(client, dialog_id)
    peer_key = str(dialog_id)
    print(f"[delete] peer={_mask_peer(peer_key)} ids={message_ids}", file=sys.stderr)
    deleted = await _with_flood_retry(client.delete_messages(peer, message_ids, revoke=revoke))
    if isinstance(deleted, list):
        count = sum(getattr(d, "pts_count", 0) for d in deleted) or len(message_ids)
    else:
        count = getattr(deleted, "pts_count", len(message_ids))
    return {"deleted": count}


async def tg_search(
    client: TelegramClient, query: str, dialog_id: int | str | None = None, limit: int = 20
) -> list:
    peer = await resolve_peer(client, dialog_id) if dialog_id else None
    messages = await client.get_messages(peer, search=query, limit=limit)
    return [_message_to_dict(m) for m in messages]


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
    if username.startswith("@"):
        username = username[1:]
    entity = await client.get_entity(username)
    title = getattr(entity, "title", None) or getattr(entity, "first_name", "") or ""
    return {
        "id": entity.id,
        "kind": _peer_kind(entity),
        "title": title,
    }


# ============================================================================
# Block A — Media send/receive
# ============================================================================


async def _send_file_internal(
    client: TelegramClient,
    dialog_id: int | str,
    file: str | list[str],
    *,
    caption: str | list[str] | None = None,
    reply_to: int | None = None,
    silent: bool = False,
    force_document: bool = False,
    voice_note: bool = False,
    video_note: bool = False,
    supports_streaming: bool = False,
    parse_mode: str | None = None,
    album: bool = False,
    log_label: str = "send_file",
) -> dict:
    peer = await resolve_peer(client, dialog_id)
    peer_key = str(dialog_id)
    await _rate_limit(peer_key)

    if isinstance(file, list):
        resolved: str | list[str] = [_resolve_file_or_url(f) for f in file]
        first = resolved[0] if resolved else ""
    else:
        resolved = _resolve_file_or_url(file)
        first = resolved
    print(
        f"[{log_label}] peer={_mask_peer(peer_key)} file={Path(str(first)).name}",
        file=sys.stderr,
    )

    sent = await _with_flood_retry(
        client.send_file(
            peer,
            resolved,
            caption=caption,
            reply_to=reply_to,
            silent=silent,
            force_document=force_document,
            voice_note=voice_note,
            video_note=video_note,
            supports_streaming=supports_streaming,
            parse_mode=parse_mode,
        )
    )
    if isinstance(sent, list):
        return {
            "ids": [m.id for m in sent],
            "chat_id": sent[0].chat_id if sent else None,
            "count": len(sent),
        }
    return {"id": sent.id, "date": _ts(sent.date), "chat_id": sent.chat_id}


async def tg_send_photo(
    client: TelegramClient,
    dialog_id: int | str,
    file: str,
    caption: str | None = None,
    reply_to: int | None = None,
    silent: bool = False,
    parse_mode: str | None = None,
) -> dict:
    """Send a photo. `file` is an absolute path, a path relative to cwd, or an http(s) URL."""
    return await _send_file_internal(
        client,
        dialog_id,
        file,
        caption=caption,
        reply_to=reply_to,
        silent=silent,
        parse_mode=parse_mode,
        log_label="send_photo",
    )


async def tg_send_document(
    client: TelegramClient,
    dialog_id: int | str,
    file: str,
    caption: str | None = None,
    reply_to: int | None = None,
    silent: bool = False,
    parse_mode: str | None = None,
) -> dict:
    """Send a file as a document (no auto-detection). Path absolute or relative to cwd, or URL."""
    return await _send_file_internal(
        client,
        dialog_id,
        file,
        caption=caption,
        reply_to=reply_to,
        silent=silent,
        force_document=True,
        parse_mode=parse_mode,
        log_label="send_document",
    )


async def tg_send_video(
    client: TelegramClient,
    dialog_id: int | str,
    file: str,
    caption: str | None = None,
    reply_to: int | None = None,
    silent: bool = False,
    supports_streaming: bool = True,
    parse_mode: str | None = None,
) -> dict:
    """Send a video. Path absolute or relative to cwd, or URL."""
    return await _send_file_internal(
        client,
        dialog_id,
        file,
        caption=caption,
        reply_to=reply_to,
        silent=silent,
        supports_streaming=supports_streaming,
        parse_mode=parse_mode,
        log_label="send_video",
    )


async def tg_send_voice(
    client: TelegramClient,
    dialog_id: int | str,
    file: str,
    reply_to: int | None = None,
    silent: bool = False,
) -> dict:
    """Send a voice note (.ogg/.opus). Path absolute or relative to cwd, or URL."""
    return await _send_file_internal(
        client,
        dialog_id,
        file,
        reply_to=reply_to,
        silent=silent,
        voice_note=True,
        log_label="send_voice",
    )


async def tg_send_audio(
    client: TelegramClient,
    dialog_id: int | str,
    file: str,
    caption: str | None = None,
    reply_to: int | None = None,
    silent: bool = False,
) -> dict:
    """Send an audio file (mp3/etc). Path absolute or relative to cwd, or URL."""
    return await _send_file_internal(
        client,
        dialog_id,
        file,
        caption=caption,
        reply_to=reply_to,
        silent=silent,
        log_label="send_audio",
    )


async def tg_send_animation(
    client: TelegramClient,
    dialog_id: int | str,
    file: str,
    caption: str | None = None,
    reply_to: int | None = None,
    silent: bool = False,
) -> dict:
    """Send a GIF / animation. Path absolute or relative to cwd, or URL."""
    return await _send_file_internal(
        client,
        dialog_id,
        file,
        caption=caption,
        reply_to=reply_to,
        silent=silent,
        log_label="send_animation",
    )


async def tg_send_sticker(
    client: TelegramClient,
    dialog_id: int | str,
    file: str,
    reply_to: int | None = None,
    silent: bool = False,
) -> dict:
    """Send a sticker (.webp/.tgs/.webm) or re-send by file id. Path absolute or relative to cwd."""
    return await _send_file_internal(
        client,
        dialog_id,
        file,
        reply_to=reply_to,
        silent=silent,
        log_label="send_sticker",
    )


async def tg_send_media_group(
    client: TelegramClient,
    dialog_id: int | str,
    files: list[str],
    caption: str | None = None,
    reply_to: int | None = None,
    silent: bool = False,
) -> dict:
    """Send an album / media group. `files` is a list of paths or URLs (max 10)."""
    if not files:
        raise ValueError("files must contain at least one item")
    if len(files) > 10:
        raise ValueError("Telegram allows up to 10 items per media group")
    return await _send_file_internal(
        client,
        dialog_id,
        files,
        caption=caption,
        reply_to=reply_to,
        silent=silent,
        album=True,
        log_label="send_media_group",
    )


async def tg_download_media(
    client: TelegramClient,
    dialog_id: int | str,
    message_id: int,
    out_path: str | None = None,
) -> dict:
    """Download media from a message.

    out_path: directory or full filename. Absolute or relative to cwd. If a directory,
    Telethon picks the original filename. If omitted, downloads to cwd.
    Returns the saved absolute path.
    """
    peer = await resolve_peer(client, dialog_id)
    msgs = await client.get_messages(peer, ids=message_id)
    msg = msgs[0] if isinstance(msgs, list) else msgs
    if not msg or not msg.media:
        raise ValueError(f"Message {message_id} has no media")

    if out_path:
        target = Path(out_path).expanduser()
        if not target.is_absolute():
            target = Path.cwd() / target
        if target.is_dir() or str(out_path).endswith(("/", os.sep)):
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
        saved = await client.download_media(msg, file=str(target))
    else:
        saved = await client.download_media(msg, file=str(Path.cwd()))

    return {
        "saved_path": str(Path(saved).resolve()) if saved else None,
        "media_kind": _media_kind(msg),
        "size": getattr(getattr(msg, "document", None), "size", None),
    }


async def tg_get_media_info(
    client: TelegramClient, dialog_id: int | str, message_id: int
) -> dict:
    """Inspect a message's media without downloading it."""
    peer = await resolve_peer(client, dialog_id)
    msgs = await client.get_messages(peer, ids=message_id)
    msg = msgs[0] if isinstance(msgs, list) else msgs
    if not msg:
        raise ValueError(f"Message {message_id} not found")
    if not msg.media:
        return {"id": msg.id, "media_kind": None}

    info: dict[str, Any] = {
        "id": msg.id,
        "chat_id": msg.chat_id,
        "media_kind": _media_kind(msg),
        "caption": msg.text or "",
        "date": _ts(msg.date),
    }
    doc = getattr(msg, "document", None)
    photo = getattr(msg, "photo", None)
    if doc:
        info["mime_type"] = doc.mime_type
        info["size"] = doc.size
        for attr in doc.attributes or []:
            a_cls = type(attr).__name__
            if "Filename" in a_cls:
                info["file_name"] = attr.file_name
            elif "Video" in a_cls:
                info["duration"] = getattr(attr, "duration", None)
                info["width"] = getattr(attr, "w", None)
                info["height"] = getattr(attr, "h", None)
            elif "Audio" in a_cls:
                info["duration"] = getattr(attr, "duration", None)
                info["voice"] = getattr(attr, "voice", False)
                info["title"] = getattr(attr, "title", None)
                info["performer"] = getattr(attr, "performer", None)
    elif photo:
        sizes = getattr(photo, "sizes", None) or []
        biggest = max(
            (s for s in sizes if hasattr(s, "w") and hasattr(s, "h")),
            key=lambda s: getattr(s, "w", 0) * getattr(s, "h", 0),
            default=None,
        )
        if biggest:
            info["width"] = getattr(biggest, "w", None)
            info["height"] = getattr(biggest, "h", None)
    return info


# ============================================================================
# Block B — Bot interaction
# ============================================================================


async def tg_send_to_bot(
    client: TelegramClient,
    bot: int | str,
    text: str,
    silent: bool = False,
    reply_to: int | None = None,
    parse_mode: str | None = None,
) -> dict:
    """Send a message to a bot. `bot` is a numeric id or @username.

    Same as tg_send_message but rejects 'me' to avoid silent confusion.
    """
    if bot == "me":
        raise ValueError("'me' is not a bot")
    return await tg_send_message(
        client,
        bot,
        text,
        reply_to=reply_to,
        silent=silent,
        parse_mode=parse_mode,
    )


async def tg_wait_bot_reply(
    client: TelegramClient,
    bot: int | str,
    after_message_id: int | None = None,
    timeout: float = 15.0,
    poll_interval: float = 0.7,
) -> dict | None:
    """Wait for a new incoming message in the chat with `bot`.

    after_message_id: ignore messages with id <= this value. If omitted, the latest
    incoming message at call time is used as the baseline.
    Returns the new message dict (with `keyboard` field if it has inline buttons), or
    None on timeout.
    """
    peer = await resolve_peer(client, bot)

    if after_message_id is None:
        latest = await client.get_messages(peer, limit=1)
        baseline = latest[0].id if latest else 0
    else:
        baseline = after_message_id

    deadline = time.time() + max(0.5, float(timeout))
    while time.time() < deadline:
        msgs = await client.get_messages(peer, limit=5, min_id=baseline)
        for m in reversed(msgs):
            if m.id > baseline and not m.out:
                out = _message_to_dict(m)
                out["keyboard"] = _extract_keyboard(m)
                return out
        await asyncio.sleep(poll_interval)
    return None


async def tg_get_bot_keyboard(
    client: TelegramClient, dialog_id: int | str, message_id: int
) -> dict:
    """Return the inline keyboard attached to a message, as a 2D list of buttons."""
    peer = await resolve_peer(client, dialog_id)
    msgs = await client.get_messages(peer, ids=message_id)
    msg = msgs[0] if isinstance(msgs, list) else msgs
    if not msg:
        raise ValueError(f"Message {message_id} not found")
    return {
        "id": msg.id,
        "has_buttons": bool(
            getattr(msg, "reply_markup", None)
            and isinstance(msg.reply_markup, ReplyInlineMarkup)
        ),
        "keyboard": _extract_keyboard(msg),
    }


async def tg_click_inline_button(
    client: TelegramClient,
    dialog_id: int | str,
    message_id: int,
    text: str | None = None,
    data: str | None = None,
    row: int | None = None,
    col: int | None = None,
) -> dict:
    """Click an inline button on a message.

    Provide ONE of: `text` (button label), `data` (callback payload),
    or `row`+`col` (zero-based grid position).
    Returns the bot's callback answer (alert text, URL) when available.
    """
    peer = await resolve_peer(client, dialog_id)
    msgs = await client.get_messages(peer, ids=message_id)
    msg = msgs[0] if isinstance(msgs, list) else msgs
    if not msg:
        raise ValueError(f"Message {message_id} not found")
    if not getattr(msg, "reply_markup", None):
        raise ValueError(f"Message {message_id} has no inline keyboard")

    kwargs: dict[str, Any] = {}
    if data is not None:
        kwargs["data"] = data.encode("utf-8") if isinstance(data, str) else data
    elif text is not None:
        kwargs["text"] = text
    elif row is not None and col is not None:
        kwargs["i"] = row
        kwargs["j"] = col
    else:
        raise ValueError("Provide one of: text, data, or row+col")

    answer = await msg.click(**kwargs)
    out: dict[str, Any] = {"clicked": True}
    if answer is not None:
        out["alert"] = bool(getattr(answer, "alert", False))
        out["message"] = getattr(answer, "message", None) or ""
        out["url"] = getattr(answer, "url", None)
    return out


# ============================================================================
# Block C — Chats / Messages extension
# ============================================================================


async def tg_get_chat_info(client: TelegramClient, dialog_id: int | str) -> dict:
    """Return detailed info about a chat / channel / user."""
    entity = await resolve_peer(client, dialog_id) if dialog_id != "me" else await client.get_me()
    info: dict[str, Any] = {
        "id": entity.id,
        "kind": _peer_kind(entity),
        "title": getattr(entity, "title", None) or getattr(entity, "first_name", "") or "",
        "username": getattr(entity, "username", None),
    }
    if isinstance(entity, User):
        info["last_name"] = entity.last_name
        info["bot"] = bool(entity.bot)
        info["verified"] = bool(getattr(entity, "verified", False))
        info["premium"] = bool(getattr(entity, "premium", False))
    if isinstance(entity, Channel):
        info["broadcast"] = bool(entity.broadcast)
        info["megagroup"] = bool(entity.megagroup)
        info["participants_count"] = getattr(entity, "participants_count", None)
    if isinstance(entity, Chat):
        info["participants_count"] = getattr(entity, "participants_count", None)
    return info


async def tg_forward_messages(
    client: TelegramClient,
    from_dialog: int | str,
    to_dialog: int | str,
    message_ids: list[int],
    silent: bool = False,
    drop_author: bool = False,
) -> dict:
    """Forward messages between dialogs."""
    if not message_ids:
        raise ValueError("message_ids must not be empty")
    src = await resolve_peer(client, from_dialog)
    dst = await resolve_peer(client, to_dialog)
    await _rate_limit(str(to_dialog))
    print(
        f"[forward] {_mask_peer(str(from_dialog))} -> {_mask_peer(str(to_dialog))} "
        f"ids={message_ids}",
        file=sys.stderr,
    )
    sent = await _with_flood_retry(
        client.forward_messages(
            dst, message_ids, src, silent=silent, drop_author=drop_author
        )
    )
    if isinstance(sent, list):
        return {"ids": [m.id for m in sent], "count": len(sent)}
    return {"ids": [sent.id], "count": 1}


async def tg_pin_message(
    client: TelegramClient,
    dialog_id: int | str,
    message_id: int,
    notify: bool = False,
    pm_oneside: bool = False,
) -> dict:
    """Pin a message in a dialog."""
    peer = await resolve_peer(client, dialog_id)
    await _with_flood_retry(
        client(
            UpdatePinnedMessageRequest(
                peer=peer,
                id=message_id,
                silent=not notify,
                pm_oneside=pm_oneside,
            )
        )
    )
    return {"ok": True, "pinned_id": message_id}


async def tg_unpin_message(
    client: TelegramClient, dialog_id: int | str, message_id: int | None = None
) -> dict:
    """Unpin a specific message, or all pinned messages when message_id is omitted."""
    peer = await resolve_peer(client, dialog_id)
    if message_id is None:
        await client.unpin_message(peer)
        return {"ok": True, "unpinned": "all"}
    await _with_flood_retry(
        client(
            UpdatePinnedMessageRequest(
                peer=peer,
                id=message_id,
                unpin=True,
            )
        )
    )
    return {"ok": True, "unpinned_id": message_id}


async def tg_get_pinned_messages(
    client: TelegramClient, dialog_id: int | str, limit: int = 20
) -> list:
    """Return pinned messages in a dialog."""
    peer = await resolve_peer(client, dialog_id)
    messages = await client.get_messages(peer, limit=limit, filter=InputMessagesFilterPinned)
    return [_message_to_dict(m) for m in messages]


# ============================================================================
# Block D — Reactions / Users / Groups / Utils
# ============================================================================


async def tg_set_reaction(
    client: TelegramClient,
    dialog_id: int | str,
    message_id: int,
    emoji: str | None,
    big: bool = False,
) -> dict:
    """Set or clear a reaction on a message.

    emoji: a single emoji string like '👍'. Pass None or '' to remove the reaction.
    """
    peer = await resolve_peer(client, dialog_id)
    reactions = []
    if emoji:
        reactions = [ReactionEmoji(emoticon=emoji)]
    await _with_flood_retry(
        client(
            SendReactionRequest(
                peer=peer,
                msg_id=message_id,
                reaction=reactions,
                big=big,
            )
        )
    )
    return {"ok": True, "emoji": emoji or None}


async def tg_get_message_reactions(
    client: TelegramClient, dialog_id: int | str, message_ids: list[int]
) -> list:
    """Return reaction counts per message."""
    if not message_ids:
        return []
    peer = await resolve_peer(client, dialog_id)
    msgs = await client.get_messages(peer, ids=message_ids)
    if not isinstance(msgs, list):
        msgs = [msgs]
    out = []
    for m in msgs:
        if not m:
            continue
        counts: list[dict[str, Any]] = []
        reactions = getattr(m, "reactions", None)
        if reactions and getattr(reactions, "results", None):
            for r in reactions.results:
                emoticon = getattr(r.reaction, "emoticon", None) or getattr(
                    r.reaction, "document_id", None
                )
                counts.append({"reaction": str(emoticon), "count": r.count})
        out.append({"id": m.id, "reactions": counts})
    return out


async def tg_get_user_info(client: TelegramClient, user: int | str) -> dict:
    """Detailed user info. `user` is a numeric id, @username, or 'me'."""
    if user == "me":
        entity = await client.get_me()
    else:
        entity = await resolve_peer(client, user)
    if not isinstance(entity, User):
        raise ValueError(f"Entity {user} is not a user")
    return {
        "id": entity.id,
        "first_name": entity.first_name or "",
        "last_name": entity.last_name or "",
        "username": entity.username,
        "phone": entity.phone or None,
        "bot": bool(entity.bot),
        "premium": bool(getattr(entity, "premium", False)),
        "verified": bool(getattr(entity, "verified", False)),
        "scam": bool(getattr(entity, "scam", False)),
        "fake": bool(getattr(entity, "fake", False)),
        "language_code": getattr(entity, "lang_code", None),
    }


async def tg_download_profile_photo(
    client: TelegramClient, user: int | str, out_path: str | None = None
) -> dict:
    """Download a user's profile photo. Returns saved path or None if no photo."""
    if user == "me":
        entity = await client.get_me()
    else:
        entity = await resolve_peer(client, user)

    if out_path:
        target = Path(out_path).expanduser()
        if not target.is_absolute():
            target = Path.cwd() / target
        if target.is_dir() or str(out_path).endswith(("/", os.sep)):
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
        saved = await client.download_profile_photo(entity, file=str(target))
    else:
        saved = await client.download_profile_photo(entity, file=str(Path.cwd()))

    return {"saved_path": str(Path(saved).resolve()) if saved else None}


async def tg_join_chat(client: TelegramClient, chat: int | str) -> dict:
    """Join a public chat by @username, channel id, or t.me invite hash."""
    if isinstance(chat, str) and chat.startswith("+"):
        # Private invite hash
        invite_hash = chat[1:]
        await _with_flood_retry(client(ImportChatInviteRequest(invite_hash)))
        return {"ok": True, "via": "invite_hash"}
    if isinstance(chat, str) and "t.me/+" in chat:
        invite_hash = chat.split("t.me/+", 1)[1].rstrip("/")
        await _with_flood_retry(client(ImportChatInviteRequest(invite_hash)))
        return {"ok": True, "via": "invite_hash"}

    entity = await resolve_peer(client, chat)
    await _with_flood_retry(client(JoinChannelRequest(entity)))
    return {"ok": True, "via": "username", "id": entity.id}


async def tg_leave_chat(client: TelegramClient, chat: int | str) -> dict:
    """Leave a channel or supergroup."""
    entity = await resolve_peer(client, chat)
    await _with_flood_retry(client(LeaveChannelRequest(entity)))
    return {"ok": True, "id": entity.id}


async def tg_list_participants(
    client: TelegramClient,
    chat: int | str,
    limit: int = 100,
    search: str = "",
) -> list:
    """List participants of a channel/supergroup. `search` filters by username/name."""
    entity = await resolve_peer(client, chat)
    if not isinstance(entity, (Channel, Chat)):
        raise ValueError("tg_list_participants only works on groups/channels")

    out = []
    async for p in client.iter_participants(
        entity,
        limit=limit,
        search=search,
        filter=ChannelParticipantsSearch(search) if search else ChannelParticipantsRecent(),
    ):
        out.append(
            {
                "id": p.id,
                "first_name": getattr(p, "first_name", "") or "",
                "last_name": getattr(p, "last_name", "") or "",
                "username": getattr(p, "username", None),
                "bot": bool(getattr(p, "bot", False)),
                "premium": bool(getattr(p, "premium", False)),
            }
        )
    return out


async def tg_typing(
    client: TelegramClient,
    dialog_id: int | str,
    action: str = "typing",
    cancel: bool = False,
) -> dict:
    """Send a typing / upload-photo / record-voice / etc. action.

    action: typing | upload_photo | upload_document | record_voice | record_video | cancel
    """
    peer = await resolve_peer(client, dialog_id)
    action_map = {
        "typing": SendMessageTypingAction(),
        "upload_photo": SendMessageUploadPhotoAction(progress=0),
        "upload_document": SendMessageUploadDocumentAction(progress=0),
        "record_voice": SendMessageRecordAudioAction(),
        "record_video": SendMessageRecordVideoAction(),
        "cancel": SendMessageCancelAction(),
    }
    if cancel:
        act = SendMessageCancelAction()
    else:
        if action not in action_map:
            raise ValueError(
                f"action must be one of: {', '.join(action_map.keys())}"
            )
        act = action_map[action]
    await client(SetTypingRequest(peer=peer, action=act))
    return {"ok": True, "action": "cancel" if cancel else action}


async def tg_set_online_status(client: TelegramClient, online: bool = True) -> dict:
    """Set the account's online presence. offline=True hides last-seen activity."""
    await client(UpdateStatusRequest(offline=not online))
    return {"ok": True, "online": online}


async def tg_get_me(client: TelegramClient) -> dict:
    """Return the authorized user's identity."""
    me = await client.get_me()
    return {
        "id": me.id,
        "first_name": me.first_name or "",
        "last_name": me.last_name or "",
        "username": me.username,
        "phone": me.phone or None,
        "premium": bool(getattr(me, "premium", False)),
        "verified": bool(getattr(me, "verified", False)),
    }
