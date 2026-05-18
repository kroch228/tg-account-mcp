from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from tg_account_mcp.client import SESSION_PATH, SESSION_DIR


async def interactive_auth() -> None:
    load_dotenv()
    api_id = os.environ.get("TG_API_ID")
    api_hash = os.environ.get("TG_API_HASH")
    phone = os.environ.get("TG_PHONE")
    password = os.environ.get("TG_2FA_PASSWORD")

    if not api_id or not api_hash or not phone:
        print("ERROR: Set TG_API_ID, TG_API_HASH, TG_PHONE in .env or environment.")
        sys.exit(1)

    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(SESSION_PATH), int(api_id), api_hash)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"Already authorized as {me.first_name} (@{me.username})")
        await client.disconnect()
        return

    await client.send_code_request(phone)
    code = input("Enter the code you received: ").strip()

    try:
        await client.sign_in(phone, code)
    except SessionPasswordNeededError:
        if password:
            await client.sign_in(password=password)
        else:
            pwd = input("2FA password required: ").strip()
            await client.sign_in(password=pwd)

    me = await client.get_me()
    print(f"Authorized as {me.first_name} (@{me.username})")
    print(f"Session saved to {SESSION_PATH}.session")

    session_file = SESSION_PATH.with_suffix(".session")
    if session_file.exists():
        session_file.chmod(0o600)

    await client.disconnect()


def main() -> None:
    asyncio.run(interactive_auth())


if __name__ == "__main__":
    main()
