from __future__ import annotations

import os
import time
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv()

SESSION_DIR = Path(__file__).resolve().parent.parent.parent / ".tg-session"
SESSION_DIR.mkdir(parents=True, exist_ok=True)
SESSION_PATH = SESSION_DIR / "user"

_entity_cache: dict[str, tuple[float, object]] = {}
CACHE_TTL = 60


def _get_config() -> tuple[int, str, str]:
    api_id = os.environ.get("TG_API_ID")
    api_hash = os.environ.get("TG_API_HASH")
    phone = os.environ.get("TG_PHONE")
    if not api_id or not api_hash or not phone:
        raise RuntimeError("TG_API_ID, TG_API_HASH, and TG_PHONE must be set in environment")
    return int(api_id), api_hash, phone


def get_client() -> TelegramClient:
    api_id, api_hash, _ = _get_config()
    return TelegramClient(str(SESSION_PATH), api_id, api_hash)


async def ensure_authorized(client: TelegramClient) -> None:
    if not client.is_connected():
        await client.connect()
    if await client.is_user_authorized():
        return
    raise RuntimeError("Session not authorized. Run `python -m tg_account_mcp.auth` first.")


async def resolve_entity(client: TelegramClient, dialog_id: int | str):
    cache_key = str(dialog_id)
    now = time.time()
    if cache_key in _entity_cache:
        ts, entity = _entity_cache[cache_key]
        if now - ts < CACHE_TTL:
            return entity
    entity = await client.get_entity(dialog_id)
    _entity_cache[cache_key] = (now, entity)
    return entity


async def resolve_peer(client: TelegramClient, dialog_id: int | str):
    if dialog_id == "me":
        return "me"
    if isinstance(dialog_id, str) and dialog_id.startswith("@"):
        return await resolve_entity(client, dialog_id[1:])
    if isinstance(dialog_id, str) and dialog_id.lstrip("-").isdigit():
        dialog_id = int(dialog_id)
    return await resolve_entity(client, dialog_id)
