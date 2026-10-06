"""
Load code config from config/codes.yaml.
Config-driven: add new codes in YAML without code changes.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


def _config_path() -> Path:
    base = Path(__file__).resolve().parent.parent
    return base / "config" / "codes.yaml"


def load_codes() -> Dict[str, Any]:
    # Static codes.yaml plus config/dynamic_codes.yaml (entries added via /addcode in Telegram).
    from .code_store import load_merged_codes

    return load_merged_codes()


def get_code_config(code: str) -> Optional[Dict[str, Any]]:
    codes = load_codes()
    return codes.get(code.upper().strip())


def format_group_name(code: str, company: str) -> Optional[str]:
    cfg = get_code_config(code)
    if not cfg:
        return None
    fmt = cfg.get("name_format")
    if not fmt:
        return None
    return fmt.format(company=company.strip())


def get_members(code: str) -> List[str]:
    cfg = get_code_config(code)
    if not cfg:
        return []
    skip = {username_for_telegram(x) for x in (cfg.get("skip_invite") or [])}
    out: List[str] = []
    seen = set()
    for name in cfg.get("members") or []:
        key = username_for_telegram(name)
        if key in skip or key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def should_auto_add_creator(code: str) -> bool:
    cfg = get_code_config(code)
    if not cfg:
        return False
    return bool(cfg.get("auto_add_creator"))


def get_skip_invite_labels(code: str) -> List[str]:
    cfg = get_code_config(code)
    if not cfg:
        return []
    return list(cfg.get("skip_invite") or [])


def get_admins(code: str) -> List[str]:
    cfg = get_code_config(code)
    if not cfg:
        return []
    return list(cfg.get("admins") or [])


def get_welcome_message(code: str, company: str = "") -> str:
    cfg = get_code_config(code)
    if not cfg:
        return ""
    text = (cfg.get("welcome") or "").strip()
    if text and "{company}" in text and company:
        text = text.format(company=company.strip())
    return text


def username_for_telegram(name: str) -> str:
    """Telegram usernames are [a-z0-9_]. Normalize display names like 'tom buttler' -> 'tom_buttler'."""
    s = name.strip().lower().replace(" ", "_")
    return "".join(c for c in s if c.isalnum() or c == "_")
