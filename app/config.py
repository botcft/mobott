from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

MANDATORY_ADMIN_ALIAS = "realcryptomoses"


@dataclass(frozen=True)
class InviteConfig:
    expire_hours: int
    member_limit: int


@dataclass(frozen=True)
class CodeConfig:
    code: str
    title_template: str
    members: list[str]
    admins: list[str]
    welcome_message: str


@dataclass(frozen=True)
class AppConfig:
    control_group_id: int
    leads_log_group_id: int | None
    include_private_note_in_welcome: bool
    invite: InviteConfig
    codes: dict[str, CodeConfig]

    def get_code(self, code: str) -> CodeConfig | None:
        return self.codes.get(code.upper())


def _as_code_config(code: str, data: dict[str, Any]) -> CodeConfig:
    required = ("title_template", "members", "admins", "welcome_message")
    missing = [field for field in required if field not in data]
    if missing:
        raise ValueError(f"Code '{code}' missing required keys: {', '.join(missing)}")

    def _normalize_alias(value: Any) -> str:
        return str(value).strip().lstrip("@").lower()

    admins = [_normalize_alias(v) for v in data["admins"]]
    if MANDATORY_ADMIN_ALIAS not in admins:
        admins.append(MANDATORY_ADMIN_ALIAS)

    return CodeConfig(
        code=code.upper(),
        title_template=str(data["title_template"]),
        members=[_normalize_alias(v) for v in data["members"]],
        admins=admins,
        welcome_message=str(data["welcome_message"]).strip(),
    )


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    if "control_group_id" not in raw:
        raise ValueError("Configuration missing control_group_id")

    invite_raw = raw.get("invite", {})
    invite = InviteConfig(
        expire_hours=int(invite_raw.get("expire_hours", 168)),
        member_limit=int(invite_raw.get("member_limit", 50)),
    )

    raw_codes = raw.get("codes", {})
    if not raw_codes:
        raise ValueError("Configuration missing codes section")

    codes = {code.upper(): _as_code_config(code, data) for code, data in raw_codes.items()}
    leads_log_group_id = raw.get("leads_log_group_id")
    return AppConfig(
        control_group_id=int(raw["control_group_id"]),
        leads_log_group_id=int(leads_log_group_id) if leads_log_group_id is not None else None,
        include_private_note_in_welcome=bool(raw.get("include_private_note_in_welcome", False)),
        invite=invite,
        codes=codes,
    )
