"""Append-only log of /new group creations (audit trail)."""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _log_path() -> Path:
    base = Path(__file__).resolve().parent.parent
    data = base / "data"
    data.mkdir(parents=True, exist_ok=True)
    return data / "group_creations.jsonl"


def log_group_creation(
    *,
    code: str,
    company: str,
    group_title: str,
    invite_link: str,
    creator_user_id: Optional[int],
    creator_username: Optional[str],
    creator_name: Optional[str],
    chat_id: Optional[int],
    members_added: list,
    members_failed: list,
    admins_promoted: list,
    admins_failed: list,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    row = {
        "at": datetime.now(timezone.utc).isoformat(),
        "code": code,
        "company": company,
        "group_title": group_title,
        "invite_link": invite_link,
        "creator_user_id": creator_user_id,
        "creator_username": creator_username,
        "creator_name": creator_name,
        "command_chat_id": chat_id,
        **(extra or {}),
        "members_added": members_added,
        "members_failed": members_failed,
        "admins_promoted": admins_promoted,
        "admins_failed": admins_failed,
    }
    path = _log_path()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
