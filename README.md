# Telegram Group Automation

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
