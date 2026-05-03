"""
Bot command handler: /new CODE Company Name
Validates code, triggers Telethon group creation, replies to control group with summary + QR.
"""
import logging
from html import escape
from typing import Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .config_loader import format_group_name, get_code_config, load_codes
from .qr_utils import qr_image_bytes
from .telethon_service import create_group_and_setup

logger = logging.getLogger(__name__)

# Short description for /start (plain text to avoid parse errors)
START_MESSAGE = """👋 Hi! I'm the Group Automation bot.

Use me in the control group to create new Telegram groups in one command.

Commands:
/new CODE CompanyName — Create a group (e.g. /new TMTP Acme)
/addcode — Add a new CODE (saved on server; open to anyone)

Codes: TEST, TMTP, TMTE, FDF, FE, NBSC, NBSDF, CRUSHC (+ any you add via /addcode).

Tap a button below for the full code list or to learn how to run the add-code wizard."""


def _start_reply_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📋 Available codes", callback_data="start_codes")],
            [InlineKeyboardButton("➕ Add a code (wizard)", callback_data="start_addcode")],
        ]
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start — show welcome and available commands."""
    message = update.effective_message
    if not message:
        return
    try:
        logger.info("/start from chat_id=%s", update.effective_chat.id if update.effective_chat else None)
        await message.reply_text(START_MESSAGE, reply_markup=_start_reply_keyboard())
    except Exception as e:
        logger.exception("Failed to send /start reply: %s", e)


async def callback_start_codes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inline button: list all codes from merged config."""
    query = update.callback_query
    if not query or not query.message:
        return
    await query.answer()
    codes = sorted(load_codes().keys())
    body = "\n".join(codes)
    text = f"Available codes ({len(codes)}):\n\n{body}\n\nUse:\n/new CODE Company Name"
    if len(text) > 4096:
        text = text[:4000] + "\n…(truncated)"
    await query.message.reply_text(text)


async def callback_start_addcode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inline button: explain /addcode questionnaire."""
    query = update.callback_query
    if not query or not query.message:
        return
    await query.answer()
    await query.message.reply_text(
        "➕ Add a new CODE — questionnaire\n\n"
        "Send this command here:\n/addcode\n\n"
        "The bot will ask you 6 steps (code → title pattern → members → admins → welcome → review), "
        "then you confirm with a Save button.\n\n"
        "Anyone can run it; codes are stored on the server in config/dynamic_codes.yaml.\n"
        "Built-in codes from codes.yaml cannot be replaced.\n\n"
        "During the wizard you can send /cancel or tap Cancel wizard."
    )


def parse_new_command(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse "/new CODE Company Name" (or "CODE Company Name" after command).
    Returns (code, company) or (None, None) if invalid.
    """
    parts = (text or "").strip().split(maxsplit=1)
    if len(parts) < 2:
        return None, None
    code = parts[0].strip().upper()
    company = parts[1].strip()
    if not code or not company:
        return None, None
    return code, company


async def cmd_new(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    telethon_client,
    control_group_id: Optional[int] = None,
) -> None:
    """
    Handle /new CODE Company Name in the control group.
    Uses MTProto client to create group, add members, promote admins; replies with result + QR.
    """
    if not update.message or not update.message.text:
        return

    if control_group_id is not None and update.effective_chat and update.effective_chat.id != control_group_id:
        await update.message.reply_text("This command is only allowed in the configured control group.")
        return

    code, company = parse_new_command(
        update.message.text.replace("/new", "", 1).strip()
    )
    if not code or not company:
        await update.message.reply_text(
            "Usage: /new <CODE> <Company Name>\nExample: /new TMTP Acme"
        )
        return

    if get_code_config(code) is None:
        await update.message.reply_text(f"Unknown code: {code}. Check config/codes.yaml.")
        return

    group_title = format_group_name(code, company)
    if not group_title:
        await update.message.reply_text(f"Could not build group name for code: {code}")
        return

    # Notify that work started
    status_msg = await update.message.reply_text(
        f"Creating group «{group_title}»…"
    )

    try:
        result = await create_group_and_setup(
            telethon_client,
            code,
            company,
            group_title,
        )
    except Exception as e:
        logger.exception("Group creation failed")
        await status_msg.edit_text(f"Error creating group: {e}")
        return

    if not result.success:
        await status_msg.edit_text(
            f"Failed to create group: {result.error}"
        )
        return

    # HTML caption: invite links often contain "_" which breaks Telegram Markdown.
    link = result.invite_link
    lines = [
        f"✅ Group created: <b>{escape(result.group_name)}</b>",
        f'🔗 Invite: <a href="{escape(link)}">{escape(link)}</a>',
        f"👥 Members added: {escape(', '.join(result.members_added) or '—')}",
        f"🛡 Admins promoted: {escape(', '.join(result.admins_promoted) or '—')}",
    ]
    if result.members_failed:
        lines.append(f"⚠ Members not added: {escape(', '.join(result.members_failed))}")
    if result.admins_failed:
        lines.append(f"⚠ Admins not promoted: {escape(', '.join(result.admins_failed))}")

    summary = "\n".join(lines)

    # Send QR as photo, then summary (or summary with photo in one message)
    qr_bytes = qr_image_bytes(result.invite_link)
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=qr_bytes,
        caption=summary,
        parse_mode="HTML",
    )
    await status_msg.delete()
