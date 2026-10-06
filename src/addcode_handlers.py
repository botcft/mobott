"""
/addcode — questionnaire wizard: anyone can register a new CODE in config/dynamic_codes.yaml.
Built-in codes from codes.yaml cannot be replaced here.
"""
import logging

from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from .code_store import (
    admins_subset_of_members,
    code_reserved,
    is_valid_code_word,
    parse_username_list,
    save_dynamic_entry,
)
from .log_channel import post_code_change_log

logger = logging.getLogger(__name__)

CODE, FORMAT, MEMBERS, ADMINS, WELCOME, CONFIRM = range(6)
TOTAL_STEPS = 6


def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("✖ Cancel wizard", callback_data="addcode_cancel")]]
    )


def _confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Save this code", callback_data="addcode_confirm")],
            [InlineKeyboardButton("✖ Cancel", callback_data="addcode_cancel")],
        ]
    )


async def addcode_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message:
        return ConversationHandler.END
    args = context.args or []
    if args:
        code = args[0].strip().upper()
        if not is_valid_code_word(code):
            await update.message.reply_text(
                "Invalid code. Use 2–32 characters: letters, numbers, underscores only.\n"
                "Try: /addcode YOURCODE",
            )
            return ConversationHandler.END
        if code_reserved(code):
            await update.message.reply_text(
                f"{code} is a built-in code (on the server). Pick a different code word.",
            )
            return ConversationHandler.END
        context.user_data["addcode"] = {"code": code}
        await update.message.reply_text(
            f"📝 Step 2/{TOTAL_STEPS} — How the group name is built\n\n"
            f"You chose code: {code}\n\n"
            "Later, people will run:\n"
            f"/new {code} Some Company Name\n\n"
            "Whatever they type after the code (here: «Some Company Name») is the company name.\n\n"
            "You must now send one line that will become the Telegram group title.\n"
            "On that line, type the five characters {company} exactly once — "
            "that is: open brace {  then the word company  then close brace }.\n"
            "That spot is where «Some Company Name» will be plugged in automatically.\n\n"
            "Full example line you could send:\n"
            "{company} X My Brand (Partnership)\n\n"
            "If someone then runs /new with Acme, the group title becomes:\n"
            "Acme X My Brand (Partnership)",
            reply_markup=_cancel_kb(),
        )
        return FORMAT

    await update.message.reply_text(
        f"📝 Step 1/{TOTAL_STEPS} — Code word\n\n"
        "This questionnaire creates a new /new CODE on the server.\n\n"
        "Reply with the code only: letters, numbers, underscore — 2 to 32 characters.\n"
        "Example: TSTSTS\n\n"
        "You can also send /cancel anytime.",
        reply_markup=_cancel_kb(),
    )
    return CODE


async def addcode_receive_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return CODE
    code = update.message.text.strip().upper().replace(" ", "")
    if not is_valid_code_word(code):
        await update.message.reply_text(
            f"📝 Step 1/{TOTAL_STEPS}\n\n"
            "That does not look valid. Use 2–32 characters: A–Z, 0–9, _ only.\n"
            "Send the code again, or tap Cancel wizard.",
            reply_markup=_cancel_kb(),
        )
        return CODE
    if code_reserved(code):
        await update.message.reply_text(
            f"📝 Step 1/{TOTAL_STEPS}\n\n"
            f"{code} is built-in on the server. Pick another code word.",
            reply_markup=_cancel_kb(),
        )
        return CODE
    context.user_data["addcode"] = {"code": code}
    await update.message.reply_text(
        f"📝 Step 2/{TOTAL_STEPS} — How the group name is built\n\n"
        f"Code for this session: {code}\n\n"
        "People will later run:\n"
        f"/new {code} Some Company Name\n\n"
        "The text after the code («Some Company Name») is the company name.\n\n"
        "Send one line: your future group title, but put {company} (brace-company-brace) "
        "where that company name should go.\n\n"
        "Example line:\n"
        "{company} X My Brand (Partnership)\n\n"
        "So /new … Acme → title: Acme X My Brand (Partnership)",
        reply_markup=_cancel_kb(),
    )
    return FORMAT


async def addcode_receive_format(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return FORMAT
    text = update.message.text.strip()
    if "{company}" not in text:
        await update.message.reply_text(
            f"📝 Step 2/{TOTAL_STEPS}\n\n"
            "Your line is missing the placeholder {company}.\n\n"
            "That placeholder means: «put the company name from /new here».\n"
            "Type it exactly: character { then company then } — nothing else between the braces.\n\n"
            "Copy this example and change only the words after {company} if you like:\n"
            "{company} X My Brand (Partnership)",
            reply_markup=_cancel_kb(),
        )
        return FORMAT
    context.user_data["addcode"]["name_format"] = text
    await update.message.reply_text(
        f"📝 Step 3/{TOTAL_STEPS} — Members\n\n"
        "Who should be invited into every new group for this code?\n\n"
        "Reply with Telegram usernames without @, separated by commas or spaces.\n\n"
        "Example: alice, bob_smith",
        reply_markup=_cancel_kb(),
    )
    return MEMBERS


async def addcode_receive_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return MEMBERS
    members = parse_username_list(update.message.text)
    if not members:
        await update.message.reply_text(
            f"📝 Step 3/{TOTAL_STEPS}\n\n"
            "Need at least one member. Send usernames again.",
            reply_markup=_cancel_kb(),
        )
        return MEMBERS
    context.user_data["addcode"]["members"] = members
    await update.message.reply_text(
        f"📝 Step 4/{TOTAL_STEPS} — Admins\n\n"
        "Who should be promoted to admin in the new group?\n\n"
        "Every admin must match someone in your member list.\n"
        "Reply with usernames (no @), comma or space separated.\n\n"
        "Example: alice",
        reply_markup=_cancel_kb(),
    )
    return ADMINS


async def addcode_receive_admins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return ADMINS
    admins = parse_username_list(update.message.text)
    if not admins:
        await update.message.reply_text(
            f"📝 Step 4/{TOTAL_STEPS}\n\n"
            "Need at least one admin. Send usernames again.",
            reply_markup=_cancel_kb(),
        )
        return ADMINS
    members = context.user_data["addcode"]["members"]
    if not admins_subset_of_members(members, admins):
        await update.message.reply_text(
            f"📝 Step 4/{TOTAL_STEPS}\n\n"
            "Every admin must appear in your members list (same username).\n"
            "Fix the list and send again.",
            reply_markup=_cancel_kb(),
        )
        return ADMINS
    context.user_data["addcode"]["admins"] = admins
    await update.message.reply_text(
        f"📝 Step 5/{TOTAL_STEPS} — Welcome message\n\n"
        "What should be posted once in the new group after it is created?\n\n"
        "• Reply with your welcome text (can be several lines).\n"
        "• Or send /skip for no welcome message.",
        reply_markup=_cancel_kb(),
    )
    return WELCOME


async def addcode_show_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    d = context.user_data.get("addcode")
    if not d:
        if update.effective_message:
            await update.effective_message.reply_text("Session lost. Start again with /addcode.")
        return ConversationHandler.END
    w = (d.get("welcome") or "").strip()
    preview = w if len(w) <= 500 else w[:500] + "…"
    members_s = ", ".join(d["members"])
    admins_s = ", ".join(d["admins"])
    summary = (
        f"📝 Step 6/{TOTAL_STEPS} — Review & save\n\n"
        f"Code: {d['code']}\n"
        f"Title pattern:\n{d['name_format']}\n\n"
        f"Members: {members_s}\n"
        f"Admins: {admins_s}\n\n"
        f"Welcome:\n{preview if preview else '(none)'}\n\n"
        "Tap Save this code to write it to the server, or Cancel."
    )
    msg = update.effective_message
    if msg:
        await msg.reply_text(summary, reply_markup=_confirm_kb())
    return CONFIRM


async def addcode_receive_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or update.message.text is None:
        return WELCOME
    text = update.message.text.strip()
    if len(text) > 3500:
        await update.message.reply_text(
            f"📝 Step 5/{TOTAL_STEPS}\n\n"
            "That message is too long (max 3500 characters). Shorten and send again, or /skip.",
            reply_markup=_cancel_kb(),
        )
        return WELCOME
    context.user_data["addcode"]["welcome"] = text
    return await addcode_show_confirm(update, context)


async def addcode_skip_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if "addcode" in context.user_data:
        context.user_data["addcode"]["welcome"] = ""
    return await addcode_show_confirm(update, context)


async def addcode_confirm_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await query.answer()
    d = context.user_data.get("addcode")
    if not d:
        await query.edit_message_text("Session expired. Send /addcode again.")
        return ConversationHandler.END
    entry = {
        "name_format": d["name_format"],
        "members": d["members"],
        "admins": d["admins"],
        "welcome": (d.get("welcome") or "").strip(),
    }
    code = d["code"]
    try:
        save_dynamic_entry(code, entry)
    except OSError as e:
        logger.exception("save_dynamic_entry failed")
        await query.edit_message_text(f"Could not save on server:\n{e}", reply_markup=None)
        return ConversationHandler.END
    context.user_data.pop("addcode", None)
    await query.edit_message_text(
        f"✅ Saved code {code}.\n\n"
        f"Anyone can create a group with:\n/new {code} Company Name",
        reply_markup=None,
    )
    logger.info("Dynamic code saved: %s", code)
    actor = update.effective_user
    who = f"@{actor.username}" if actor and actor.username else (str(actor.id) if actor else "unknown")
    await post_code_change_log(
        context.bot,
        "Code added",
        f"Code: <b>{escape(code)}</b>\nBy: {escape(who)}",
    )
    return ConversationHandler.END


async def addcode_inline_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer("Cancelled")
        context.user_data.pop("addcode", None)
        try:
            await query.edit_message_text("Wizard cancelled.", reply_markup=None)
        except Exception:
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
    else:
        context.user_data.pop("addcode", None)
    return ConversationHandler.END


async def addcode_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("addcode", None)
    if update.message:
        await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


def build_addcode_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        name="addcode",
        entry_points=[CommandHandler("addcode", addcode_start)],
        states={
            CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, addcode_receive_code)],
            FORMAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, addcode_receive_format)],
            MEMBERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, addcode_receive_members)],
            ADMINS: [MessageHandler(filters.TEXT & ~filters.COMMAND, addcode_receive_admins)],
            WELCOME: [
                CommandHandler("skip", addcode_skip_welcome),
                MessageHandler(filters.TEXT & ~filters.COMMAND, addcode_receive_welcome),
            ],
            CONFIRM: [
                CallbackQueryHandler(addcode_confirm_save, pattern=r"^addcode_confirm$"),
                CallbackQueryHandler(addcode_inline_cancel, pattern=r"^addcode_cancel$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", addcode_cancel),
            CallbackQueryHandler(addcode_inline_cancel, pattern=r"^addcode_cancel$"),
        ],
        per_chat=True,
        per_user=True,
        allow_reentry=True,
    )
