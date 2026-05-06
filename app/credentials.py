"""Resolve Telegram bot + MTProto credentials from the environment."""

from __future__ import annotations

import os


def telegram_credentials_from_env() -> tuple[str, int, str]:
    """BOT_TOKEN or TELEGRAM_BOT_TOKEN, plus TELEGRAM_API_ID / TELEGRAM_API_HASH."""
    bot_token = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not bot_token:
        raise RuntimeError(
            "Set BOT_TOKEN (or TELEGRAM_BOT_TOKEN) to your @BotFather token. "
            "On Railway: Service → Variables."
        )
    if "replace_me" in bot_token.lower():
        raise RuntimeError(
            "BOT_TOKEN is still a placeholder (see .env.example). "
            "Replace it with the real token from @BotFather in Railway Variables."
        )

    api_id_raw = (os.getenv("TELEGRAM_API_ID") or "").strip()
    api_hash = (os.getenv("TELEGRAM_API_HASH") or "").strip()
    if not api_id_raw or not api_hash:
        raise RuntimeError("TELEGRAM_API_ID and TELEGRAM_API_HASH are required.")
    if "replace_me" in api_hash.lower():
        raise RuntimeError(
            "TELEGRAM_API_HASH is still a placeholder. Set your real api_hash from "
            "https://my.telegram.org in Railway Variables."
        )

    try:
        api_id = int(api_id_raw)
    except ValueError as exc:
        raise RuntimeError("TELEGRAM_API_ID must be an integer.") from exc

    return bot_token, api_id, api_hash
