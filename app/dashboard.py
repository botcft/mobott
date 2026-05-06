from __future__ import annotations

import base64
import io
import json
import os
import shutil
from contextlib import asynccontextmanager
from html import escape

import qrcode
from dotenv import load_dotenv
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from telegram import Bot

from app.config import AppConfig, load_config
from app.credentials import telegram_credentials_from_env
from app.db import Database, Registration
from app.telegram_service import TelegramUserService


class DashboardState:
    def __init__(self, config: AppConfig, db: Database, mtproto: TelegramUserService, bot: Bot) -> None:
        self.config = config
        self.db = db
        self.mtproto = mtproto
        self.bot = bot
        self.bot_username = ""
        self.mtproto_ready = False
        self.flash_message = ""
        self.flash_error = False

    def set_flash(self, message: str, *, error: bool = False) -> None:
        self.flash_message = message
        self.flash_error = error

    def pop_flash(self) -> tuple[str, bool]:
        message = self.flash_message
        is_error = self.flash_error
        self.flash_message = ""
        self.flash_error = False
        return message, is_error


def _build_qr_base64(url: str) -> str:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _build_qr_stream(url: str) -> io.BytesIO:
    data = io.BytesIO(base64.b64decode(_build_qr_base64(url)))
    data.name = "invite-qr.png"
    data.seek(0)
    return data


def _select_users(
    registrations: dict[str, Registration], aliases: list[str]
) -> list[tuple[str, int, str | None]]:
    return [
        (alias, registrations[alias].user_id, registrations[alias].username)
        for alias in aliases
        if alias in registrations
    ]


def _layout(content: str) -> str:
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Telegram Automation Dashboard</title>
    <style>
      :root {{
        color-scheme: dark;
        --bg: #060916;
        --card: rgba(18, 24, 43, 0.75);
        --border: rgba(129, 154, 255, 0.22);
        --text: #e7ecff;
        --muted: #9cabd8;
        --accent: #75a1ff;
        --accent-2: #7bf3d0;
        --danger: #ff7f9d;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        background: radial-gradient(circle at 10% 10%, #122041 0%, #060916 50%, #04060f 100%);
        color: var(--text);
        font: 14px/1.45 "Inter", "Segoe UI", Roboto, Arial, sans-serif;
      }}
      .shell {{
        max-width: 1280px;
        margin: 30px auto;
        padding: 0 20px 30px;
      }}
      .hero {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 18px;
      }}
      h1 {{
        margin: 0;
        letter-spacing: 0.3px;
        font-size: 26px;
      }}
      .subtitle {{
        color: var(--muted);
      }}
      .grid {{
        display: grid;
        grid-template-columns: repeat(12, 1fr);
        gap: 14px;
      }}
      .card {{
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 16px;
        backdrop-filter: blur(10px);
        box-shadow: 0 14px 28px rgba(0, 0, 0, 0.25);
      }}
      .kpi {{
        grid-column: span 3;
      }}
      .kpi strong {{
        display: block;
        font-size: 28px;
        color: var(--accent-2);
        margin-top: 6px;
      }}
      .create {{ grid-column: span 6; }}
      .register {{ grid-column: span 6; }}
      .groups {{ grid-column: span 7; }}
      .audit {{ grid-column: span 5; }}
      label {{
        display: block;
        margin: 8px 0 5px;
        color: var(--muted);
      }}
      input, select {{
        width: 100%;
        border: 1px solid var(--border);
        background: #0b1227;
        color: var(--text);
        border-radius: 9px;
        padding: 10px 12px;
      }}
      button {{
        margin-top: 12px;
        border: none;
        border-radius: 10px;
        padding: 10px 14px;
        background: linear-gradient(90deg, var(--accent), #9f86ff);
        color: white;
        font-weight: 600;
        cursor: pointer;
      }}
      table {{
        width: 100%;
        border-collapse: collapse;
        margin-top: 8px;
        font-size: 13px;
      }}
      th, td {{
        text-align: left;
        border-bottom: 1px solid rgba(129, 154, 255, 0.16);
        padding: 8px 6px;
        vertical-align: top;
      }}
      th {{ color: var(--muted); font-weight: 600; }}
      .badge {{
        display: inline-block;
        border: 1px solid rgba(123, 243, 208, 0.4);
        color: var(--accent-2);
        padding: 2px 8px;
        border-radius: 99px;
        font-size: 12px;
      }}
      .flash {{
        margin: 8px 0 14px;
        padding: 10px 12px;
        border-radius: 10px;
        border: 1px solid var(--border);
        background: rgba(117, 161, 255, 0.12);
      }}
      .flash.error {{
        border-color: rgba(255, 127, 157, 0.4);
        background: rgba(255, 127, 157, 0.12);
        color: #ffd6e1;
      }}
      .qr {{
        width: 160px;
        border-radius: 12px;
        border: 1px solid var(--border);
        background: white;
        padding: 10px;
      }}
      .mono {{
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
        font-size: 12px;
      }}
      @media (max-width: 1000px) {{
        .kpi, .create, .register, .groups, .audit {{ grid-column: span 12; }}
      }}
    </style>
  </head>
  <body>
    <div class="shell">{content}</div>
  </body>
</html>"""


def create_dashboard_app() -> FastAPI:
    load_dotenv()
    bot_token, api_id, api_hash = telegram_credentials_from_env()
    bot_session = os.getenv("TELETHON_SESSION_BOT", os.getenv("TELETHON_SESSION", "group_creator.session"))
    telethon_session = os.getenv("TELETHON_SESSION_DASHBOARD", f"{bot_session}.dashboard")
    db_path = os.getenv("DB_PATH", "automation.db")
    config_path = os.getenv("CONFIG_PATH", "config/groups.yaml")

    if not os.path.exists(telethon_session) and os.path.exists(bot_session):
        # Use a dedicated dashboard session file to avoid sqlite locks with bot process.
        shutil.copy2(bot_session, telethon_session)

    config = load_config(config_path)
    db = Database(db_path)
    mtproto = TelegramUserService(session=telethon_session, api_id=api_id, api_hash=api_hash)
    bot = Bot(token=bot_token)
    state = DashboardState(config=config, db=db, mtproto=mtproto, bot=bot)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        me = await state.bot.get_me()
        state.bot_username = me.username or ""
        await state.mtproto.connect()
        state.mtproto_ready = await state.mtproto.is_authorized()
        try:
            yield
        finally:
            await state.mtproto.stop()

    app = FastAPI(title="Telegram Automation Dashboard", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    async def dashboard() -> HTMLResponse:
        flash_message, flash_error = state.pop_flash()
        recent_groups = state.db.list_recent_groups(limit=12)
        recent_audit = state.db.list_recent_audit(limit=15)

        codes = "".join(
            f"<option value='{escape(code)}'>{escape(code)} - {escape(cfg.title_template)}</option>"
            for code, cfg in sorted(state.config.codes.items())
        )
        flash = (
            f"<div class='flash {'error' if flash_error else ''}'>{escape(flash_message)}</div>"
            if flash_message
            else ""
        )
        groups_rows = "".join(
            "<tr>"
            f"<td><span class='badge'>{escape(row['code'])}</span></td>"
            f"<td>{escape(row['group_name'])}</td>"
            f"<td>{escape(row['private_note'] or '-')}</td>"
            f"<td>{escape(row['created_by_name'] or '-')}</td>"
            f"<td>{escape(row['created_at'])}</td>"
            f"<td class='mono'>{escape(row['invite_link'] or '-')}</td>"
            "</tr>"
            for row in recent_groups
        )
        audit_rows = "".join(
            "<tr>"
            f"<td>{escape(row['created_at'])}</td>"
            f"<td>{escape(row['action'])}</td>"
            f"<td>{escape(row['actor_name'] or str(row['actor_user_id']))}</td>"
            "</tr>"
            for row in recent_audit
        )

        html = _layout(
            f"""
            <div class="hero">
              <div>
                <h1>Telegram Group Automation</h1>
                <div class="subtitle">Futuristic control center for group creation and operations</div>
              </div>
              <div class="subtitle">Bot: @{escape(state.bot_username or 'unknown')} | MTProto: {("ready" if state.mtproto_ready else "session required")}</div>
            </div>
            {flash}
            {"<div class='flash error'>MTProto session is not authorized yet. Run <span class='mono'>py -m app.bootstrap_session</span> once, then restart the dashboard.</div>" if not state.mtproto_ready else ""}
            <div class="grid">
              <div class="card kpi"><div>Total Registrations</div><strong>{state.db.count_registrations()}</strong></div>
              <div class="card kpi"><div>Total Groups</div><strong>{state.db.count_groups()}</strong></div>
              <div class="card kpi"><div>Configured Codes</div><strong>{len(state.config.codes)}</strong></div>
              <div class="card kpi"><div>Control Group</div><strong class="mono">{state.config.control_group_id}</strong></div>
              <div class="card kpi"><div>Leads Log Group</div><strong class="mono">{state.config.leads_log_group_id or "not set"}</strong></div>

              <div class="card create">
                <h3>Create Group</h3>
                <form method="post" action="/create-group">
                  <label>Code</label>
                  <select name="code" required>{codes}</select>
                  <label>Company Name</label>
                  <input type="text" name="company" placeholder="Acme" required />
                  <label>Private Note (optional)</label>
                  <input type="text" name="private_note" placeholder="Warm lead from event intro" />
                  <label>Operator Name (for audit)</label>
                  <input type="text" name="operator_name" placeholder="shaheer" required />
                  <label>Operator User ID (for audit)</label>
                  <input type="number" name="operator_user_id" placeholder="123456789" required />
                  <button type="submit">Create Group</button>
                </form>
              </div>

              <div class="card register">
                <h3>Register/Update Teammate</h3>
                <form method="post" action="/register-user">
                  <label>Alias</label>
                  <input type="text" name="alias" placeholder="shaheer" required />
                  <label>User ID</label>
                  <input type="number" name="user_id" placeholder="123456789" required />
                  <label>Username (optional)</label>
                  <input type="text" name="username" placeholder="shaheer_handle" />
                  <label>First Name (optional)</label>
                  <input type="text" name="first_name" placeholder="Shaheer" />
                  <button type="submit">Save Registration</button>
                </form>
              </div>

              <div class="card groups">
                <h3>Recent Groups</h3>
                <table>
                  <thead><tr><th>Code</th><th>Group</th><th>Private Note</th><th>Created By</th><th>Created At</th><th>Invite</th></tr></thead>
                  <tbody>{groups_rows or "<tr><td colspan='6'>No groups yet.</td></tr>"}</tbody>
                </table>
              </div>

              <div class="card audit">
                <h3>Audit Trail</h3>
                <table>
                  <thead><tr><th>Time</th><th>Action</th><th>Actor</th></tr></thead>
                  <tbody>{audit_rows or "<tr><td colspan='3'>No logs yet.</td></tr>"}</tbody>
                </table>
              </div>
            </div>
            """
        )
        return HTMLResponse(content=html)

    @app.post("/register-user")
    async def register_user(
        alias: str = Form(...),
        user_id: int = Form(...),
        username: str | None = Form(default=None),
        first_name: str | None = Form(default=None),
    ) -> RedirectResponse:
        clean_alias = alias.strip().lower().lstrip("@")
        clean_username = username.strip().lower() if username and username.strip() else None
        clean_first_name = first_name.strip() if first_name and first_name.strip() else None
        state.db.upsert_registration(
            alias=clean_alias,
            user_id=user_id,
            username=clean_username,
            first_name=clean_first_name,
        )
        state.db.append_audit(
            actor_user_id=user_id,
            actor_name=clean_alias,
            action="dashboard_register",
            payload_json=json.dumps({"alias": clean_alias, "username": clean_username}),
        )
        state.set_flash(f"Saved registration for '{clean_alias}'.")
        return RedirectResponse(url="/", status_code=303)

    @app.post("/create-group", response_class=HTMLResponse)
    async def create_group(
        code: str = Form(...),
        company: str = Form(...),
        private_note: str | None = Form(default=None),
        operator_name: str = Form(...),
        operator_user_id: int = Form(...),
    ) -> RedirectResponse:
        chosen_code = code.strip().upper()
        company_name = company.strip()
        private_note_text = private_note.strip() if private_note and private_note.strip() else None
        if not state.mtproto_ready:
            state.set_flash(
                "MTProto session is not authorized. Run 'py -m app.bootstrap_session' once in terminal, then restart dashboard.",
                error=True,
            )
            return RedirectResponse(url="/", status_code=303)
        if not company_name:
            state.set_flash("Company name is required.", error=True)
            return RedirectResponse(url="/", status_code=303)

        code_config = state.config.get_code(chosen_code)
        if not code_config:
            state.set_flash(f"Unknown code '{chosen_code}'.", error=True)
            return RedirectResponse(url="/", status_code=303)

        existing = state.db.find_group(code=chosen_code, company=company_name)
        if existing:
            state.set_flash(
                f"Group already exists: {existing['group_name']} (chat {existing['chat_id']}).",
                error=True,
            )
            return RedirectResponse(url="/", status_code=303)

        group_name = code_config.title_template.format(company=company_name)
        required_aliases = list(dict.fromkeys(code_config.members + code_config.admins))
        registrations = state.db.get_many_registrations(required_aliases)
        missing = [alias for alias in required_aliases if alias not in registrations]
        if missing:
            state.set_flash(
                "Missing registrations: " + ", ".join(missing) + ". Add them first.",
                error=True,
            )
            return RedirectResponse(url="/", status_code=303)

        added_members: list[str] = []
        failed_members: dict[str, str] = {}
        promoted_admins: list[str] = []
        failed_admins: dict[str, str] = {}
        invite_link: str | None = None
        chat_id: int | None = None
        leads_log_error: str | None = None

        try:
            created_chat = await state.mtproto.create_supergroup(
                title=group_name,
                about=f"{chosen_code} onboarding group for {company_name}",
            )
            chat_id = int(f"-100{created_chat.id}")

            invite_aliases = list(dict.fromkeys(code_config.members + code_config.admins))
            member_entries = _select_users(registrations, invite_aliases)
            member_result = await state.mtproto.invite_many(created_chat, member_entries)
            added_members = member_result.success
            failed_members = member_result.failed

            admin_entries = _select_users(registrations, code_config.admins)
            admin_result = await state.mtproto.promote_many(created_chat, admin_entries)
            promoted_admins = admin_result.success
            failed_admins = admin_result.failed

            if state.bot_username:
                try:
                    await state.mtproto.add_bot_as_admin(created_chat, state.bot_username)
                except Exception as exc:  # noqa: BLE001
                    leads_log_error = (
                        f"Could not add/promote bot in created group ({exc}). "
                        "Invite link may be unavailable."
                    )

            try:
                invite = await state.bot.create_chat_invite_link(chat_id=chat_id)
                invite_link = invite.invite_link
            except Exception as exc:  # noqa: BLE001
                if leads_log_error:
                    leads_log_error += f" Invite link creation failed: {exc}"
                else:
                    leads_log_error = f"Invite link creation failed: {exc}"

            state.db.record_group(
                chat_id=chat_id,
                code=chosen_code,
                company=company_name,
                group_name=group_name,
                invite_link=invite_link,
                private_note=private_note_text,
                created_by_user_id=operator_user_id,
                created_by_name=operator_name.strip(),
            )

            state.db.append_audit(
                actor_user_id=operator_user_id,
                actor_name=operator_name.strip(),
                action="dashboard_create_group",
                payload_json=json.dumps(
                    {
                        "code": chosen_code,
                        "company": company_name,
                        "chat_id": chat_id,
                        "group_name": group_name,
                        "invite_link": invite_link,
                        "private_note": private_note_text,
                        "added_members": added_members,
                        "failed_members": failed_members,
                        "promoted_admins": promoted_admins,
                        "failed_admins": failed_admins,
                    }
                ),
            )

            summary_text = (
                f"Group created: {group_name}\n"
                f"Code: {chosen_code}\n"
                f"Invite link: {invite_link or 'not available'}\n"
                f"Private note: {private_note_text or 'none'}\n"
                f"Members added: {', '.join(added_members) if added_members else 'none'}\n"
                f"Admins promoted: {', '.join(promoted_admins) if promoted_admins else 'none'}"
            )
            if state.config.leads_log_group_id:
                try:
                    await state.bot.send_message(chat_id=state.config.leads_log_group_id, text=summary_text)
                    if invite_link:
                        await state.bot.send_photo(
                            chat_id=state.config.leads_log_group_id,
                            photo=_build_qr_stream(invite_link),
                            caption=f"Lead QR - {group_name}",
                        )
                except Exception as exc:  # noqa: BLE001
                    if leads_log_error:
                        leads_log_error += f" Leads log post failed: {exc}"
                    else:
                        leads_log_error = f"Leads log post failed: {exc}"
        except Exception as exc:  # noqa: BLE001
            state.set_flash(f"Failed to create group: {exc}", error=True)
            return RedirectResponse(url="/", status_code=303)

        qr_html = ""
        if invite_link:
            qr = _build_qr_base64(invite_link)
            qr_html = (
                "<div style='margin-top:12px'>"
                "<div class='subtitle'>Invite QR</div>"
                f"<img class='qr' src='data:image/png;base64,{qr}' alt='Invite QR' />"
                "</div>"
            )

        summary = (
            f"""
            <div class="hero">
              <div>
                <h1>Group Created</h1>
                <div class="subtitle">Your workspace is ready.</div>
              </div>
              <div><a href="/" style="color:#9ec0ff">Back to dashboard</a></div>
            </div>
            <div class="card">
              <p><strong>Group:</strong> {escape(group_name)}</p>
              <p><strong>Invite:</strong> <a href="{escape(invite_link or '#')}" style="color:#9ec0ff">{escape(invite_link or 'not available')}</a></p>
              <p><strong>Private Note:</strong> {escape(private_note_text or "none")}</p>
              <p><strong>Members Added:</strong> {escape(", ".join(added_members) if added_members else "none")}</p>
              <p><strong>Admins Promoted:</strong> {escape(", ".join(promoted_admins) if promoted_admins else "none")}</p>
              <p><strong>Member Failures:</strong> {escape(str(failed_members) if failed_members else "none")}</p>
              <p><strong>Admin Failures:</strong> {escape(str(failed_admins) if failed_admins else "none")}</p>
              <p><strong>Warnings:</strong> {escape(leads_log_error or "none")}</p>
              {qr_html}
            </div>
            """
        )
        return HTMLResponse(content=_layout(summary))

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_dashboard_app()
