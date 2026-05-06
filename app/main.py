from __future__ import annotations

import io
import json
import logging
import os
from dataclasses import dataclass

import qrcode
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import Conflict
from telegram.ext import (
    Application,
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.config import AppConfig, load_config
from app.db import Database, Registration
from app.telegram_service import TelegramUserService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
logger = logging.getLogger(__name__)


START_CALLBACK_PREFIX = "start:"


@dataclass
class ServiceContainer:
    config: AppConfig
    db: Database
    mtproto: TelegramUserService


def _services(context: ContextTypes.DEFAULT_TYPE) -> ServiceContainer:
    return context.application.bot_data["services"]  # type: ignore[return-value]


def _start_main_text() -> str:
    return (
        "Telegram Group Automation - Control Center\n\n"
        "What this bot does:\n"
        "- Creates a new Telegram group from one command\n"
        "- Uses code rules for naming, members, admins, and welcome message\n"
        "- Generates invite link + QR code\n"
        "- Sends results back to control group\n"
        "- Logs everything for audit\n\n"
        "Main command:\n"
        "/new <CODE> <Company Name> [--note <private note>]\n"
        "Example:\n"
        "/new TEST3 Acme --note Warm lead from event intro\n\n"
        "3-user TEST setup currently configured:\n"
        "- tmtaimanager (admin)\n"
        "- realcryptomoses (admin)\n"
        "- tmtaisupportkhubaib\n"
        "- tmtaisupportmoeed\n\n"
        "Important:\n"
        "1) All test users must run /register once.\n"
        "2) /new only works in control_group_id.\n"
        "3) If a code requires users not registered, creation will stop with clear error."
    )


def _start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("How It Works", callback_data=f"{START_CALLBACK_PREFIX}how"),
                InlineKeyboardButton("3-User Test Plan", callback_data=f"{START_CALLBACK_PREFIX}test3"),
            ],
            [
                InlineKeyboardButton("Register Steps", callback_data=f"{START_CALLBACK_PREFIX}register"),
                InlineKeyboardButton("Creation Flow", callback_data=f"{START_CALLBACK_PREFIX}flow"),
            ],
            [
                InlineKeyboardButton("Control/Log IDs", callback_data=f"{START_CALLBACK_PREFIX}ids"),
                InlineKeyboardButton("Welcome + Notes", callback_data=f"{START_CALLBACK_PREFIX}welcome"),
            ],
            [
                InlineKeyboardButton(
                    "Prefill /new TEST3",
                    switch_inline_query_current_chat="/new TEST3 Acme --note Warm lead from event intro",
                )
            ],
        ]
    )


def _start_section_text(section: str) -> str:
    if section == "how":
        return (
            "How it works\n\n"
            "1) You send /new CODE CompanyName in control group.\n"
            "2) Bot validates code and required aliases.\n"
            "3) MTProto user creates the group.\n"
            "4) Members are invited.\n"
            "5) Admins are promoted.\n"
            "6) Bot creates invite link + QR and reports result.\n"
            "7) New joiners receive code-specific welcome message."
        )
    if section == "test3":
        return (
            "3-user test plan\n\n"
            "Use CODE: TEST3\n"
            "Expected members: tmtaimanager, tmtaisupportkhubaib, tmtaisupportmoeed\n"
            "Expected admins: tmtaimanager, realcryptomoses\n\n"
            "Steps:\n"
            "- Each test account runs /register <alias>\n"
            "- In control group run: /new TEST3 Acme --note test run\n"
            "- Verify group name, members, admin, invite, QR, and logs."
        )
    if section == "register":
        return (
            "Register steps\n\n"
            "Each teammate should run one of:\n"
            "/register tmtaimanager\n"
            "/register tmtaisupportkhubaib\n"
            "/register tmtaisupportmoeed\n\n"
            "Tips:\n"
            "- Alias matching is case-insensitive.\n"
            "- @alias also works.\n"
            "- Registration saves user_id for reliable invites."
        )
    if section == "flow":
        return (
            "Creation flow details\n\n"
            "Command format:\n"
            "/new <CODE> <Company Name> [--note <private note>]\n\n"
            "Supported currently include TEST3 + your live codes.\n"
            "If duplicate CODE+Company exists, bot returns existing group info instead of creating a second one."
        )
    if section == "ids":
        return (
            "Control and leads log IDs\n\n"
            "Bot only accepts /new in control_group_id from config/groups.yaml.\n"
            "leads_log_group_id receives summary + QR after creation.\n\n"
            "If IDs are placeholders, /new appears to do nothing useful.\n"
            "Set real IDs and restart bot after editing config."
        )
    if section == "welcome":
        return (
            "Welcome + private notes\n\n"
            "Welcome message is pulled from code config.\n"
            "Private note is saved during /new and shown in output.\n"
            "Optional config: include_private_note_in_welcome=true to append note context in welcome message."
        )
    return _start_main_text()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    await message.reply_text(_start_main_text(), reply_markup=_start_keyboard())


async def start_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data or ""
    section = data.replace(START_CALLBACK_PREFIX, "", 1)
    text = _start_section_text(section)
    await query.edit_message_text(text=text, reply_markup=_start_keyboard())


def _actor(update: Update) -> tuple[int, str | None]:
    user = update.effective_user
    if not user:
        return 0, None
    display = user.username or user.full_name
    return user.id, display


def _parse_new_args(command_args: list[str]) -> tuple[str, str, str | None] | None:
    if len(command_args) < 2:
        return None
    code = command_args[0].upper().strip()
    remainder = " ".join(command_args[1:]).strip()
    note: str | None = None
    company = remainder
    if " --note " in f" {remainder}":
        company, note = remainder.split(" --note ", maxsplit=1)
    elif " | " in remainder:
        company, note = remainder.split(" | ", maxsplit=1)
    company = company.strip()
    note = note.strip() if note else None
    if note == "":
        note = None
    if not company:
        return None
    return code, company, note


async def on_startup(app: Application) -> None:
    services: ServiceContainer = app.bot_data["services"]
    await services.mtproto.start()
    me = await app.bot.get_me()
    app.bot_data["bot_username"] = me.username or ""
    logger.info("Started automation bot as @%s", app.bot_data["bot_username"])


async def on_shutdown(app: Application) -> None:
    services: ServiceContainer = app.bot_data["services"]
    await services.mtproto.stop()
    logger.info("Stopped MTProto client.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = _services(context)
    codes = ", ".join(sorted(services.config.codes.keys()))
    message = (
        "Use /new <CODE> <Company Name> in the control group.\n"
        "Optional private note: /new <CODE> <Company> --note <text>\n"
        "Run /register <alias> once so the system can add you by ID.\n"
        f"Supported codes: {codes}"
    )
    await update.effective_message.reply_text(message)


async def whereami_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    message = update.effective_message
    if not chat or not message:
        return
    chat_title = chat.title or "(no title)"
    chat_username = f"@{chat.username}" if chat.username else "(none)"
    await message.reply_text(
        "Current chat details\n\n"
        f"chat_id: `{chat.id}`\n"
        f"type: `{chat.type}`\n"
        f"title: {chat_title}\n"
        f"username: {chat_username}"
    )


async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = _services(context)
    user = update.effective_user
    if not user:
        return

    if context.args:
        alias = " ".join(context.args).strip().lower()
    elif user.username:
        alias = user.username.lower()
    else:
        alias = user.first_name.strip().lower()
    alias = alias.lstrip("@").strip()

    services.db.upsert_registration(
        alias=alias,
        user_id=user.id,
        username=user.username.lower() if user.username else None,
        first_name=user.first_name,
    )
    services.db.append_audit(
        actor_user_id=user.id,
        actor_name=user.username or user.full_name,
        action="register",
        payload_json=json.dumps({"alias": alias}),
    )
    await update.effective_message.reply_text(f"Registered as {alias} with user id {user.id}.")


async def new_group_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = _services(context)
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return

    actor_id, actor_name = _actor(update)

    if chat.id != services.config.control_group_id:
        await message.reply_text("This command only works in the configured control group.")
        return

    parsed = _parse_new_args(context.args)
    if not parsed:
        await message.reply_text("Usage: /new <CODE> <Company Name> [--note <private note>]")
        return
    code, company, private_note = parsed
    if not private_note:
        private_note = _replied_text(message)

    code_config = services.config.get_code(code)
    if not code_config:
        available_codes = ", ".join(sorted(services.config.codes.keys()))
        await message.reply_text(f"Unknown code {code}. Supported: {available_codes}")
        return

    existing = services.db.find_group(code=code, company=company)
    if existing:
        await message.reply_text(
            "Group already exists for this code/company.\n"
            f"Name: {existing['group_name']}\n"
            f"Chat ID: {existing['chat_id']}\n"
            f"Invite: {existing['invite_link'] or 'not available'}"
        )
        return

    group_name = code_config.title_template.format(company=company)
    required_aliases = list(dict.fromkeys(code_config.members + code_config.admins))
    registrations = services.db.get_many_registrations(required_aliases)
    missing = [alias for alias in required_aliases if alias not in registrations]
    if missing:
        await message.reply_text(
            "Cannot continue. Missing registrations for: "
            + ", ".join(alias for alias in missing)
            + ".\nAsk them to run /register <alias> first."
        )
        return

    status = await message.reply_text(
        f"Creating {group_name}...\nThis usually takes a few seconds."
    )

    chat_id: int | None = None
    invite_link: str | None = None
    create_error: str | None = None
    added_members: list[str] = []
    failed_members: dict[str, str] = {}
    promoted_admins: list[str] = []
    failed_admins: dict[str, str] = {}

    try:
        created_chat = await services.mtproto.create_supergroup(
            title=group_name,
            about=f"{code} onboarding group for {company}",
        )
        chat_id = int(f"-100{created_chat.id}")

        invite_aliases = list(dict.fromkeys(code_config.members + code_config.admins))
        member_entries = _select_users(registrations, invite_aliases)
        member_result = await services.mtproto.invite_many(created_chat, member_entries)
        added_members = member_result.success
        failed_members = member_result.failed

        admin_entries = _select_users(registrations, code_config.admins)
        admin_result = await services.mtproto.promote_many(created_chat, admin_entries)
        promoted_admins = admin_result.success
        failed_admins = admin_result.failed

        bot_username = context.application.bot_data.get("bot_username", "")
        if bot_username:
            try:
                await services.mtproto.add_bot_as_admin(created_chat, bot_username)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to add/promote bot in new group: %s", exc)

        try:
            invite = await context.bot.create_chat_invite_link(
                chat_id=chat_id,
                expire_date=services.mtproto.invite_expiry(services.config.invite.expire_hours),
                member_limit=services.config.invite.member_limit,
                creates_join_request=False,
            )
            invite_link = invite.invite_link
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to create invite link via bot API: %s", exc)

        services.db.record_group(
            chat_id=chat_id,
            code=code,
            company=company,
            group_name=group_name,
            invite_link=invite_link,
            private_note=private_note,
            created_by_user_id=actor_id,
            created_by_name=actor_name,
        )

        services.db.append_audit(
            actor_user_id=actor_id,
            actor_name=actor_name,
            action="create_group",
            payload_json=json.dumps(
                {
                    "code": code,
                    "company": company,
                    "chat_id": chat_id,
                    "group_name": group_name,
                    "invite_link": invite_link,
                    "private_note": private_note,
                    "added_members": added_members,
                    "failed_members": failed_members,
                    "promoted_admins": promoted_admins,
                    "failed_admins": failed_admins,
                }
            ),
        )
    except Exception as exc:  # noqa: BLE001
        create_error = str(exc)
        logger.exception("Failed to create group for code %s and company %s", code, company)

    if create_error:
        await status.edit_text(f"Failed to create group {group_name}:\n{create_error}")
        return

    result_text = (
        f"Group created: {group_name}\n"
        f"Code: {code}\n"
        f"Invite link: {invite_link or 'not created'}\n"
        f"Private note: {private_note or 'none'}\n"
        f"Members added: {', '.join(added_members) if added_members else 'none'}\n"
        f"Admins promoted: {', '.join(promoted_admins) if promoted_admins else 'none'}"
    )
    if failed_members:
        result_text += (
            "\nMember add failures: "
            + "; ".join(f"{name} ({reason})" for name, reason in failed_members.items())
        )
    if failed_admins:
        result_text += (
            "\nAdmin promote failures: "
            + "; ".join(f"{name} ({reason})" for name, reason in failed_admins.items())
        )

    await status.edit_text(result_text)

    if invite_link:
        qr_bytes = _build_qr_png(invite_link)
        await context.bot.send_photo(
            chat_id=chat.id,
            photo=qr_bytes,
            caption="Invite link QR code",
        )
        if services.config.leads_log_group_id and services.config.leads_log_group_id != chat.id:
            await context.bot.send_message(
                chat_id=services.config.leads_log_group_id,
                text=result_text,
            )
            await context.bot.send_photo(
                chat_id=services.config.leads_log_group_id,
                photo=_build_qr_png(invite_link),
                caption=f"Lead QR - {group_name}",
            )


def _build_qr_png(url: str) -> io.BytesIO:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    data = io.BytesIO()
    data.name = "invite-qr.png"
    img.save(data, format="PNG")
    data.seek(0)
    return data


def _select_users(
    registrations: dict[str, Registration],
    aliases: list[str],
) -> list[tuple[str, int, str | None]]:
    return [
        (alias, registrations[alias].user_id, registrations[alias].username)
        for alias in aliases
        if alias in registrations
    ]


def _replied_text(message) -> str | None:
    replied = getattr(message, "reply_to_message", None)
    if not replied:
        return None
    return (replied.text or replied.caption or "").strip() or None


def _render_welcome_message(
    template: str, company: str, private_note: str | None, include_private_note: bool
) -> str:
    try:
        rendered = template.format(company=company)
    except KeyError:
        rendered = template
    if include_private_note and private_note:
        rendered = f"{rendered}\n\nContext: {private_note}"
    return rendered


async def welcome_new_members(update: Update, context: CallbackContext) -> None:
    services = _services(context)
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return
    if not message.new_chat_members:
        return

    group_row = services.db.get_group(chat.id)
    if not group_row:
        return
    code = str(group_row["code"])
    code_config = services.config.get_code(code)
    if not code_config:
        return

    welcome = _render_welcome_message(
        code_config.welcome_message,
        company=str(group_row["company"]),
        private_note=str(group_row["private_note"]) if group_row["private_note"] else None,
        include_private_note=services.config.include_private_note_in_welcome,
    )
    await message.reply_text(welcome)


async def app_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    if isinstance(error, Conflict):
        logger.warning(
            "Telegram 409 Conflict: another bot instance is polling this token."
        )
        return
    logger.exception("Unhandled bot error: %s", error)


def build_app() -> Application:
    load_dotenv()
    bot_token = os.getenv("BOT_TOKEN")
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    telethon_session = os.getenv(
        "TELETHON_SESSION_BOT",
        os.getenv("TELETHON_SESSION", "group_creator.session"),
    )
    db_path = os.getenv("DB_PATH", "automation.db")
    config_path = os.getenv("CONFIG_PATH", "config/groups.yaml")

    if not bot_token:
        raise RuntimeError("BOT_TOKEN is required.")
    if not api_id or not api_hash:
        raise RuntimeError("TELEGRAM_API_ID and TELEGRAM_API_HASH are required.")

    config = load_config(config_path)
    db = Database(db_path)
    mtproto = TelegramUserService(session=telethon_session, api_id=int(api_id), api_hash=api_hash)
    services = ServiceContainer(config=config, db=db, mtproto=mtproto)

    app = Application.builder().token(bot_token).build()
    app.bot_data["services"] = services

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("whereami", whereami_command))
    app.add_handler(CommandHandler("register", register_command))
    app.add_handler(CommandHandler("new", new_group_command))
    app.add_handler(CallbackQueryHandler(start_callback_handler, pattern=f"^{START_CALLBACK_PREFIX}"))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members))
    app.add_error_handler(app_error_handler)

    app.post_init = on_startup
    app.post_shutdown = on_shutdown
    return app


def main() -> None:
    app = build_app()
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
