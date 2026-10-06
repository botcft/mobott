"""
Bot command handler: /new CODE Company Name
Validates code, triggers Telethon group creation, replies to control group with summary + QR.
"""
import logging
import os
from html import escape
from typing import Optional, Tuple

from telegram import User

from telegram import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeDefault,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

# Shown in Telegram’s “/” menu (keep in sync with CommandHandlers in main.py).
BOT_COMMANDS = [
    BotCommand("start", "Start the bot and see commands"),
    BotCommand("new", "Create group: /new CODE CompanyName"),
    BotCommand("addcode", "Add a new CODE (wizard; saved on server)"),
    BotCommand("deletecode", "Remove a bot-added CODE (/addcode only)"),
    BotCommand("cancel", "Cancel the /addcode wizard"),
    BotCommand("skip", "Skip welcome message during /addcode"),
]


async def register_bot_commands(bot) -> None:
    """Publish slash commands to Telegram (private chats and groups)."""
    for scope in (BotCommandScopeDefault(), BotCommandScopeAllGroupChats()):
        await bot.set_my_commands(BOT_COMMANDS, scope=scope)


from .config_loader import format_group_name, get_code_config, load_codes
from .creation_log import log_group_creation
from .log_channel import post_group_created_log
from .qr_utils import qr_image_bytes
from .telethon_service import create_group_and_setup

logger = logging.getLogger(__name__)

# Short description for /start (plain text to avoid parse errors)
START_MESSAGE = """👋 Hi! I'm the Group Automation bot.

Use me in the control group to create new Telegram groups.

Create a group (either way):
• TMTP Acme Company
• /new TMTP Acme Company

Commands:
/start — This menu
/new CODE CompanyName — Create a group (e.g. /new CCP Acme)
/addcode — Add a new CODE (saved on server; open to anyone)
/deletecode — Remove a code added via /addcode (built-in codes stay)
/cancel — Cancel the /addcode wizard
/skip — Skip welcome message (during /addcode only)

Codes: TMTP, TMTE (TMT.AI), CCP (Content Crusaders), OP, PR (TOKEN2049) + /addcode.

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
    text = f"Available codes ({len(codes)}):\n\n{body}\n\nSend:\nCODE Company Name\nor /new CODE Company Name"
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


def _user_may_run_new(user: Optional[User]) -> bool:
    """If ALLOWED_NEW_* is set, only those usernames / user ids can run /new."""
    if not user:
        return False
    ids_raw = (os.environ.get("ALLOWED_NEW_USER_IDS") or "").strip()
    if ids_raw:
        allowed_ids = set()
        for part in ids_raw.split(","):
            part = part.strip()
            if part.isdigit():
                allowed_ids.add(int(part))
        if allowed_ids and user.id in allowed_ids:
            return True
    raw = (os.environ.get("ALLOWED_NEW_USERNAMES") or "").strip()
    if not raw:
        return True
    allowed = {p.strip().lower().lstrip("@") for p in raw.split(",") if p.strip()}
    if not allowed:
        return True
    username = (user.username or "").lower()
    if username and username in allowed:
        return True
    # Username missing or wrong — still allow if user id list matches (checked above)
    if ids_raw:
        return False
    return False


def _allowlist_denial_message(user: Optional[User]) -> str:
    un = f"@{user.username}" if user and user.username else "no @username on your Telegram profile"
    uid = user.id if user else "?"
    return (
        "You are not on the allowlist to create groups.\n\n"
        f"Your account: {un} (id {uid})\n\n"
        "Ask an admin to add your @username to ALLOWED_NEW_USERNAMES in .env, "
        "or your numeric id to ALLOWED_NEW_USER_IDS, then restart the bot.\n\n"
        "Use `/new CODE Company` or `CODE Company` in the same control chat as the team."
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


def parse_plain_new(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse «CODE Company Name» without /new. Returns None if not a known code."""
    text = (text or "").strip()
    if not text or text.startswith("/"):
        return None, None
    code, company = parse_new_command(text)
    if not code or not company:
        return None, None
    if get_code_config(code) is None:
        return None, None
    return code, company


def _format_create_error(error: str) -> str:
    low = (error or "").lower()
    if "spamreported" in low:
        return (
            "Telegram blocked group creation for the creator account (spamreported).\n"
            "The bot command worked, but Telegram will not let this user create groups.\n"
            "Try @SpamBot in Telegram or appeal via Telegram Support, "
            "or log in a different creator account (login_telethon.py --qr)."
        )
    return f"Failed to create group: {error}"


async def execute_new_group(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    telethon_client,
    control_group_id: Optional[int],
    code: str,
    company: str,
) -> None:
    actor = update.effective_user
    group_title = format_group_name(code, company)
    if not group_title:
        if update.message:
            await update.message.reply_text(f"Could not build group name for code: {code}")
        return

    status_msg = await update.message.reply_text(f"Creating group «{group_title}»…")

    try:
        result = await create_group_and_setup(
            telethon_client,
            code,
            company,
            group_title,
            creator_user_id=actor.id if actor else None,
            creator_username=actor.username if actor else None,
        )
    except Exception as e:
        logger.exception("Group creation failed")
        await status_msg.edit_text(f"Error creating group: {e}")
        return

    if not result.success:
        await status_msg.edit_text(_format_create_error(result.error))
        return

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
    if result.manual_invite_notes:
        lines.append(f"📌 Manual: {escape('; '.join(result.manual_invite_notes))}")
    if actor:
        who = f"@{actor.username}" if actor.username else str(actor.id)
        lines.append(f"🧾 Created by: {escape(who)}")
    if result.creator_added:
        lines.append("➕ Creator auto-added to group (CCP).")

    summary = "\n".join(lines)

    log_group_creation(
        code=code,
        company=company,
        group_title=result.group_name,
        invite_link=link,
        creator_user_id=actor.id if actor else None,
        creator_username=actor.username if actor else None,
        creator_name=actor.full_name if actor else None,
        chat_id=update.effective_chat.id if update.effective_chat else None,
        members_added=result.members_added,
        members_failed=result.members_failed,
        admins_promoted=result.admins_promoted,
        admins_failed=result.admins_failed,
        extra={"creator_auto_added": result.creator_added},
    )

    qr_bytes = qr_image_bytes(result.invite_link)
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=qr_bytes,
        caption=summary,
        parse_mode="HTML",
    )
    await post_group_created_log(context.bot, summary, qr_bytes)
    await status_msg.delete()


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

    actor = update.effective_user
    if not _user_may_run_new(actor):
        await update.message.reply_text(_allowlist_denial_message(actor))
        return

    code, company = parse_new_command(
        update.message.text.replace("/new", "", 1).strip()
    )
    if not code or not company:
        await update.message.reply_text(
            "Usage: /new <CODE> <Company Name>\nExample: /new CCP Acme"
        )
        return

    if get_code_config(code) is None:
        await update.message.reply_text(f"Unknown code: {code}. Send /start → Available codes.")
        return

    await execute_new_group(update, context, telethon_client, control_group_id, code, company)


async def cmd_plain_new(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    telethon_client,
    control_group_id: Optional[int] = None,
) -> None:
    """Handle «CODE Company Name» without /new (legacy style)."""
    if not update.message or not update.message.text:
        return

    if control_group_id is not None and update.effective_chat and update.effective_chat.id != control_group_id:
        return

    actor = update.effective_user
    if not _user_may_run_new(actor):
        code, company = parse_plain_new(update.message.text)
        if code and company:
            await update.message.reply_text(_allowlist_denial_message(actor))
        return

    code, company = parse_plain_new(update.message.text)
    if not code or not company:
        return

    await execute_new_group(update, context, telethon_client, control_group_id, code, company)
