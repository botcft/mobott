"""
/deletecode — remove a bot-added CODE from config/dynamic_codes.yaml.
Built-in codes from codes.yaml cannot be deleted here.
"""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from .code_store import (
    code_reserved,
    delete_dynamic_code,
    is_valid_code_word,
    list_dynamic_code_keys,
)

logger = logging.getLogger(__name__)

_CONFIRM_PREFIX = "deletecode_confirm:"
_CANCEL = "deletecode_cancel"


def _confirm_kb(code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"Yes, delete {code}",
                    callback_data=f"{_CONFIRM_PREFIX}{code}",
                )
            ],
            [InlineKeyboardButton("Cancel", callback_data=_CANCEL)],
        ]
    )


async def cmd_deletecode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    args = context.args or []
    if not args:
        dynamic = list_dynamic_code_keys()
        if not dynamic:
            await message.reply_text(
                "No bot-added codes to delete.\n\n"
                "Built-in codes (TEST, TMTP, …) stay in server config and are not removed here.\n"
                "Usage: /deletecode YOURCODE"
            )
            return
        body = "\n".join(f"• {c}" for c in dynamic)
        await message.reply_text(
            "Codes you can delete (added via /addcode):\n\n"
            f"{body}\n\n"
            "Send: /deletecode CODE\n"
            "Built-in codes in codes.yaml cannot be deleted from Telegram."
        )
        return

    code = args[0].strip().upper()
    if not is_valid_code_word(code):
        await message.reply_text(
            "Invalid code. Use: /deletecode YOURCODE\n"
            "(2–32 characters: letters, numbers, underscore)"
        )
        return

    if code_reserved(code):
        await message.reply_text(
            f"{code} is a built-in code on the server. "
            "Only codes added with /addcode can be deleted here."
        )
        return

    if code not in list_dynamic_code_keys():
        await message.reply_text(
            f"{code} is not in the bot-added list (or already removed).\n"
            "Send /deletecode with no args to see deletable codes."
        )
        return

    await message.reply_text(
        f"Delete code <b>{code}</b>?\n\n"
        "/new will no longer work for this code until you add it again with /addcode.",
        parse_mode="HTML",
        reply_markup=_confirm_kb(code),
    )


async def deletecode_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not query.data.startswith(_CONFIRM_PREFIX):
        return
    code = query.data[len(_CONFIRM_PREFIX) :].strip().upper()
    await query.answer()

    if not is_valid_code_word(code) or code_reserved(code):
        await query.edit_message_text("This code cannot be deleted here.")
        return

    if delete_dynamic_code(code):
        logger.info("Dynamic code deleted: %s", code)
        await query.edit_message_text(
            f"Deleted code <b>{code}</b>.",
            parse_mode="HTML",
        )
    else:
        await query.edit_message_text(
            f"Could not delete <b>{code}</b> (not found or built-in).",
            parse_mode="HTML",
        )


async def deletecode_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer("Cancelled")
    await query.edit_message_text("Delete cancelled.")


def build_deletecode_handlers() -> list:
    return [
        CommandHandler("deletecode", cmd_deletecode),
        CallbackQueryHandler(deletecode_confirm, pattern=r"^deletecode_confirm:"),
        CallbackQueryHandler(deletecode_cancel, pattern=f"^{_CANCEL}$"),
    ]
