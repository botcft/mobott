"""Post successful bot actions to a Telegram log channel (not errors)."""
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def log_channel_id() -> Optional[int]:
    raw = (os.environ.get("LOG_CHANNEL_ID") or os.environ.get("TELEGRAM_LOG_CHANNEL_ID") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        logger.warning("LOG_CHANNEL_ID is not a valid integer: %r", raw)
        return None


async def post_log_channel(
    bot,
    text: str,
    *,
    photo_bytes: Optional[bytes] = None,
) -> None:
    """Send an audit entry to the configured log channel. Failures are logged only."""
    chat_id = log_channel_id()
    if chat_id is None:
        return
    body = text.strip()
    if not body:
        return
    try:
        if photo_bytes:
            await bot.send_photo(
                chat_id=chat_id,
                photo=photo_bytes,
                caption=body,
                parse_mode="HTML",
            )
        else:
            await bot.send_message(chat_id=chat_id, text=body, parse_mode="HTML")
    except Exception as exc:
        logger.warning("Could not post to log channel %s: %s", chat_id, exc)


async def post_group_created_log(bot, summary_html: str, qr_bytes: bytes) -> None:
    header = "📋 <b>Group created</b>\n\n"
    await post_log_channel(bot, header + summary_html, photo_bytes=qr_bytes)


async def post_code_change_log(bot, title: str, detail_html: str) -> None:
    await post_log_channel(bot, f"📋 <b>{title}</b>\n\n{detail_html}")
