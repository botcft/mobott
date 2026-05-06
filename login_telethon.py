"""
One-time Telethon login. Run this in your terminal first:
    .venv/bin/python login_telethon.py

Use --force to delete any existing session and be asked for phone + code again:
    .venv/bin/python login_telethon.py --force

Enter your phone number (with country code, e.g. +1234567890) and the code Telegram sends.
The session is saved so main.py can start without prompting.
"""
import argparse
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
load_dotenv(".env.example")

from src.telethon_service import create_telethon_client


def _env_int(key: str):
    v = os.environ.get(key)
    if v is None:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def _remove_session(session_dir: Path, session_name: str) -> None:
    """Delete session files so Telethon will ask for phone + code again."""
    for path in session_dir.glob(f"{session_name}*"):
        path.unlink()
        print(f"Removed {path}")


async def main(force_login: bool) -> None:
    api_id = _env_int("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    if not api_id or not api_hash:
        print("Missing TELEGRAM_API_ID or TELEGRAM_API_HASH in .env")
        return

    session_dir = Path(os.environ.get("TELEGRAM_SESSION_DIR", "session"))
    session_name = "group_automation"

    if force_login:
        _remove_session(session_dir, session_name)
        print("You will now be asked for phone number and code.\n")

    client = create_telethon_client(
        api_id=api_id,
        api_hash=api_hash,
        session_name=session_name,
        session_dir=session_dir,
    )

    if not force_login:
        print("You will be asked for your Telegram phone number and login code.")
        print("Use the same account as the one from my.telegram.org (API ID/hash).\n")
    await client.start()
    me = await client.get_me()
    print(f"\nLogged in as: {me.first_name} (@{me.username or 'no username'})")
    print("Session saved.\n\nNext step (run this exact command):")
    print("  .venv/bin/python main.py")
    await client.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Log in Telethon (user account) once; session is saved for main.py")
    parser.add_argument("--force", action="store_true", help="Delete existing session and ask for phone + code again")
    args = parser.parse_args()
    asyncio.run(main(force_login=args.force))
