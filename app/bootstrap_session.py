from __future__ import annotations

import asyncio
import argparse
import os

from dotenv import load_dotenv
from telethon import TelegramClient


def _resolve_session_name(target: str) -> str:
    shared = os.getenv("TELETHON_SESSION", "group_creator.session")
    if target == "bot":
        return os.getenv("TELETHON_SESSION_BOT", shared)
    if target == "dashboard":
        return os.getenv("TELETHON_SESSION_DASHBOARD", f"{shared}.dashboard")
    return shared


async def _bootstrap(session_name: str) -> None:
    load_dotenv()
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")

    if not api_id or not api_hash:
        raise RuntimeError("TELEGRAM_API_ID and TELEGRAM_API_HASH are required in .env")

    print("Starting one-time MTProto login bootstrap...")
    print("Use your dedicated Telegram user account phone number and login code.")
    async with TelegramClient(session_name, int(api_id), api_hash) as client:
        await client.start()
        me = await client.get_me()
        print(f"Session ready for user: {me.username or me.first_name} ({me.id})")
    print(f"Session file saved: {session_name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bootstrap Telethon session file.")
    parser.add_argument(
        "--target",
        choices=("bot", "dashboard", "shared"),
        default="bot",
        help="Which session name to bootstrap from env.",
    )
    args = parser.parse_args()
    load_dotenv()
    asyncio.run(_bootstrap(_resolve_session_name(args.target)))
