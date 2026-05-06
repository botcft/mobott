# Telegram Group Automation

Config-driven Telegram automation that creates pre-configured groups from a single control-group command:

`/new <CODE> <Company Name>`

This service combines:
- **Telegram Bot API** (`python-telegram-bot`) for command handling, replies, welcome messages, and invite links.
- **Telegram MTProto user account** (`Telethon`) for group creation, member invites, and admin promotion.
- **Web dashboard** (`FastAPI`) for visual operations and management.

## Features Included

- `/new <CODE> <Company>` command in a control group.
- Optional private note in command: `/new <CODE> <Company> --note <text>` (or reply to a message and run `/new ...`).
- Group naming via code templates.
- Member and admin rules per code.
- Auto welcome messages in created groups.
- Invite link generation + QR code image.
- `/register <alias>` to map teammate aliases to Telegram IDs.
- SQLite audit trail for operations and troubleshooting.
- Retry/backoff for common Telegram transient failures.

## Project Structure

- `app/main.py` - bot app entrypoint and handlers.
- `app/telegram_service.py` - Telethon MTProto operations.
- `app/dashboard.py` - local management dashboard (web UI).
- `app/config.py` - YAML config loader and validation.
- `app/db.py` - SQLite registrations, group metadata, audit log.
- `config/groups.yaml` - code -> naming/member/admin/welcome mappings.
- `.env.example` - required environment variables.

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill values.
4. Update `config/groups.yaml`:
   - Set `control_group_id`.
   - Set `leads_log_group_id` (or keep same as control group).
   - Keep/edit code mappings as needed.

## Telegram Prerequisites

1. Create bot with `@BotFather`; set `BOT_TOKEN`.
2. Add bot to control group as admin.
3. Disable bot privacy with `/setprivacy` -> `Disable`.
4. Create or assign a dedicated MTProto user account:
   - Set `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`.
   - First run will create `TELETHON_SESSION` file (or use your configured session path).
5. Have each teammate run `/register <alias>` once in a chat where bot can see them.

## Run

### Telegram Bot Worker

`python -m app.main`

By default this uses `TELETHON_SESSION_BOT` (falls back to `TELETHON_SESSION`).

### Dashboard (Local Web UI)

`uvicorn app.dashboard:app --host 0.0.0.0 --port 8080`

Open [http://localhost:8080](http://localhost:8080)

By default this uses `TELETHON_SESSION_DASHBOARD` so it does not lock the bot session file.

### Mo bot (this repo root: `/start`, `/new`, `/addcode`)

`python main.py`

Uses `TELEGRAM_BOT_TOKEN` (or `BOT_TOKEN`) plus `TELEGRAM_API_ID` / `TELEGRAM_API_HASH`. Run from the project root so `src/` and `config/codes.yaml` exist.

### Railway

If you only run `uvicorn main:app`, Telegram **never gets polled**, so the bot will not answer in chat. Use the bundled start command instead:

- **`nixpacks.toml`** and **`Procfile`** run `scripts/railway_start.sh`, which starts **`python main.py`** in the background (polling) and then **Uvicorn** on `$PORT` for the dashboard and health checks.
- Set the same env vars as production (`TELEGRAM_BOT_TOKEN` or `BOT_TOKEN`, API id/hash). Mount or upload a **`session/`** Telethon session file if `/new` should work after deploy.
- To run **only** the web UI and skip the mo poller: set `DISABLE_MO_BOT=1`.

### One-Time MTProto Session Bootstrap

Before creating groups from bot/dashboard, run once to authorize the creator account session:

`py -m app.bootstrap_session --target bot`

If you want a separate dashboard session, run:

`py -m app.bootstrap_session --target dashboard`

Then start the bot/dashboard normally.

## Command Behavior

- `/new CODE Company Name`
  - Optional: `--note private text` for internal lead context.
  - Validates `CODE`.
  - Builds group title from template.
  - Creates a supergroup via MTProto account.
  - Invites configured members.
  - Promotes configured admins.
  - Adds/promotes the bot where possible.
  - Creates invite link via bot API.
  - Generates QR PNG and sends it to the control group.
  - Optionally posts results to `leads_log_group_id` for master lead tracking.
  - Logs full result in SQLite.

- Dashboard create-group now includes optional private note and writes to leads log group as well.

## Operational Notes

- Telegram may reject some invites due to user privacy settings.
- If MTProto cannot resolve a user by numeric ID alone, ensuring username is present in `/register` improves success.
- Duplicate names are allowed by Telegram; this implementation does not block same-name group creation.
- Keep the process running 24/7 on VPS/cloud for reliable automation.
- The dashboard writes to the same SQLite database as the bot, so both stay synchronized.

## Next Enhancements (Optional)

- Replace SQLite with Postgres for shared multi-instance deployment.
- Add command auth allowlist (who can run `/new`).
- Add health endpoint and uptime monitoring.
