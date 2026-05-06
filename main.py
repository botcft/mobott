"""
Telegram Group Automation – entry point.
Listens for /new CODE Company Name in the control group; creates group via MTProto, replies with link + QR.
"""
import asyncio
import faulthandler
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Optional

# Show we started (flush so it appears immediately)
print("Loading...", flush=True)

# Stack dump on SIGUSR1: `kill -USR1 <pid>` when the process seems stuck
if hasattr(signal, "SIGUSR1"):
    faulthandler.register(signal.SIGUSR1, chain=False)
faulthandler.enable(all_threads=True)

from dotenv import load_dotenv

# Load .env first, then .env.example so either file can supply credentials
load_dotenv()
load_dotenv(".env.example")

from telegram import BotCommand, Update
from telegram.error import InvalidToken
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from src.addcode_handlers import build_addcode_conversation_handler
from src.bot_handlers import (
    callback_start_addcode,
    callback_start_codes,
    cmd_new,
    cmd_start,
)
from src.telethon_service import create_telethon_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    force=True,
)
_root = logging.getLogger()
_log_file = Path(__file__).resolve().parent / "bot.log"
try:
    _fh = logging.FileHandler(_log_file, encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    _root.addHandler(_fh)
except OSError as _e:
    print(f"Warning: could not open {_log_file} for logging: {_e}", flush=True)


def _global_excepthook(exc_type, exc, tb):
    if exc_type is KeyboardInterrupt:
        return sys.__excepthook__(exc_type, exc, tb)
    logging.critical("Uncaught exception", exc_info=(exc_type, exc, tb))
    print(f"Fatal: {exc_type.__name__}: {exc}", flush=True)
    sys.__excepthook__(exc_type, exc, tb)


sys.excepthook = _global_excepthook
logger = logging.getLogger(__name__)


def _env_int(key: str, default: Optional[int] = None) -> Optional[int]:
    v = os.environ.get(key)
    if v is None:
        return default
    try:
        return int(v)
    except ValueError:
        return default


def main() -> None:
    print("main() started", flush=True)
    # Must run from project root (folder containing src/ and config/)
    if not Path("src").is_dir() or not Path("config/codes.yaml").exists():
        print("Run from the project folder. Example: cd '/Users/muzan/Desktop/mo bot' then .venv/bin/python main.py", flush=True)
        sys.exit(1)
    bot_token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    api_id = _env_int("TELEGRAM_API_ID")
    api_hash = (os.environ.get("TELEGRAM_API_HASH") or "").strip()

    if not bot_token:
        logger.error("Set TELEGRAM_BOT_TOKEN")
        raise SystemExit(1)
    if not api_id or not api_hash:
        logger.error("Set TELEGRAM_API_ID and TELEGRAM_API_HASH (for user account / MTProto)")
        raise SystemExit(1)

    # Optional: restrict /new to a specific control group
    control_group_id = _env_int("CONTROL_GROUP_ID")

    session_dir = Path(os.environ.get("TELEGRAM_SESSION_DIR", "session"))

    async def run_bot() -> None:
        # Build Telethon client inside this coroutine so it binds to asyncio.run()'s event loop.
        # Creating the client in sync main() before asyncio.run() leaves queues/locks on the
        # wrong loop (Python 3.9), and connect() hangs until timeout.
        telethon_client = create_telethon_client(
            api_id=api_id,
            api_hash=api_hash,
            session_name="group_automation",
            session_dir=session_dir,
        )
        logger.info("Connecting Telethon (user account)...")
        # Use connect() + is_user_authorized() to avoid start() blocking on stdin when session exists
        try:
            await asyncio.wait_for(telethon_client.connect(), timeout=60.0)
        except asyncio.TimeoutError:
            await telethon_client.disconnect()
            msg = "Telethon connection timed out. Run: .venv/bin/python login_telethon.py --force"
            logger.error(msg)
            print(msg, flush=True)
            raise RuntimeError(msg) from None
        if not await telethon_client.is_user_authorized():
            await telethon_client.disconnect()
            msg = "Session invalid or expired. Run: .venv/bin/python login_telethon.py --force"
            logger.error(msg)
            print(msg, flush=True)
            raise RuntimeError(msg)
        print("Telethon connected.", flush=True)
        logger.info("Telethon (user) client connected")

        async def handle_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            await cmd_new(update, context, telethon_client, control_group_id)

        async def post_init(app: Application) -> None:
            logger.info("Bot started")
            await app.bot.set_my_commands([
                BotCommand("start", "Start the bot and see commands"),
                BotCommand("new", "Create group: /new CODE CompanyName (e.g. /new TMTP Acme)"),
                BotCommand("addcode", "Add a new CODE (anyone; saved on server)"),
            ])

        app = (
            Application.builder()
            .token(bot_token)
            .post_init(post_init)
            .build()
        )
        app.add_handler(CallbackQueryHandler(callback_start_codes, pattern=r"^start_codes$"))
        app.add_handler(CallbackQueryHandler(callback_start_addcode, pattern=r"^start_addcode$"))
        app.add_handler(build_addcode_conversation_handler())
        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("new", handle_new))

        try:
            await app.initialize()
        except InvalidToken:
            await telethon_client.disconnect()
            logger.error("TELEGRAM_BOT_TOKEN rejected by Telegram (wrong, revoked, or typo).")
            print(
                "Invalid TELEGRAM_BOT_TOKEN. In Telegram open @BotFather → your bot → "
                "/token (or /newbot), copy the token into .env with no quotes or spaces, then run again.",
                flush=True,
            )
            raise RuntimeError("Invalid TELEGRAM_BOT_TOKEN")
        await app.start()
        bot_info = await app.bot.get_me()
        logger.info("Polling started. Bot: @%s", bot_info.username)
        print("Bot is running: @%s" % (bot_info.username or bot_info.id))
        print("In Telegram: open a chat with this bot and send /start")
        await app.updater.start_polling(drop_pending_updates=True)

        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
            await telethon_client.disconnect()

    print("Starting async bot loop...", flush=True)
    logger.info("File log: %s", _log_file.resolve())
    try:
        asyncio.run(run_bot())
    except RuntimeError as e:
        logger.exception("Bot startup failed: %s", e)
        print("Error: %s" % e, flush=True)
        raise SystemExit(1) from e
    except BaseException as e:
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            logger.info("Shutdown: %s", type(e).__name__)
            raise
        logger.exception("Bot crashed: %s", e)
        print("Error: %s" % e, flush=True)
        raise SystemExit(1) from e

if __name__ == "__main__":
    print("Entry point", flush=True)
    main()
