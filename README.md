# Telegram Group Automation

<<<<<<< HEAD
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
=======
Create structured Telegram groups from a single command in a control group: `/new <CODE> <Company Name>`.

- **Bot** handles the command and replies with group name, invite link, QR code, and member/admin summary.
- **User account (MTProto / Telethon)** creates the group, adds members, promotes admins, and sends the welcome message (bots cannot create groups or promote admins).

## Quick start

1. **Create a bot** with [@BotFather](https://t.me/BotFather), get `TELEGRAM_BOT_TOKEN`.
2. **Get API credentials** for a user account at [my.telegram.org](https://my.telegram.org/apps): `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`.
3. **Copy env and install deps:**

   ```bash
   cp .env.example .env
   # Edit .env with your values
   pip install -r requirements.txt
   ```

4. **First run (Telethon login):**  
   On first start, the script will prompt you to log in with the **user account** (phone number and code). This creates a session file so you don’t need to log in again. The **bot** does not need to be logged in separately.

5. **Run:**

   ```bash
   python main.py
   ```

6. **In your control group**, send:  
   `/new TMTP Acme`  
   The bot will create the group, add members, promote admins, send the welcome message, then reply in the control group with the invite link and QR code.

## Command

- **Format:** `/new <CODE> <Company Name>`
- **Example:** `/new TMTP Acme` → group name: `Acme X TMT.AI (Partnership)`

Codes, naming, members, admins, and welcome messages are defined in **`config/codes.yaml`**. Add or change codes there without changing code.

## Config: `config/codes.yaml`

Each code has:

- `name_format`: `{company}` is replaced by the company name.
- `members`: list of usernames to add (Telegram usernames; spaces in the config are normalized to `_`, e.g. `tom buttler` → `tom_buttler`).
- `admins`: subset of members to promote to admin.
- `welcome`: message sent once in the new group after creation.

Member names in the config must match **Telegram usernames** (without `@`). If a name has spaces in the spec (e.g. `tom buttler`), it is converted to `tom_buttler` for lookup; ensure that matches the real username or add a mapping if needed.

## Environment

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from @BotFather |
| `TELEGRAM_API_ID` | Yes | User app API ID from my.telegram.org |
| `TELEGRAM_API_HASH` | Yes | User app API hash |
| `CONTROL_GROUP_ID` | No | If set, only this chat can use `/new` |
| `TELEGRAM_SESSION_DIR` | No | Directory for Telethon session (default: `./session`) |

Load `.env` yourself (e.g. `python-dotenv`) or export the variables before running.

## Behaviour

- Creates a **supergroup** (megagroup) so history is visible and invite links work.
- Group creator (your user account) and the bot (if added) remain admins.
- Welcome message is sent **once** in the new group after creation. Per-user “on join” welcome can be added later by keeping the bot in the group and handling join events.

## Project layout

```
config/
  codes.yaml          # Code → name format, members, admins, welcome
src/
  config_loader.py    # Load and query codes.yaml
  telethon_service.py # Create group, add members, promote, invite link
  qr_utils.py         # QR code image from invite link
  bot_handlers.py     # /new command and reply to control group
main.py               # Entry: Telethon client + bot, run polling
```
>>>>>>> 79b3bcb84a79943fb8d5ba3b5a34db920c34ee64
