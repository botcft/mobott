"""
Merge static config/codes.yaml with config/dynamic_codes.yaml (bot-added codes).
"""
import re
from pathlib import Path
from typing import Any, Dict, List, Set

import yaml

_CODE_WORD = re.compile(r"^[A-Za-z0-9_]{2,32}$")


def _norm_user(name: str) -> str:
    s = name.strip().lower().replace(" ", "_")
    return "".join(c for c in s if c.isalnum() or c == "_")


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def static_codes_path() -> Path:
    return _project_root() / "config" / "codes.yaml"


def dynamic_codes_path() -> Path:
    return _project_root() / "config" / "dynamic_codes.yaml"


def static_code_keys() -> Set[str]:
    path = static_codes_path()
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {str(k).upper() for k in data.keys()}


def is_valid_code_word(code: str) -> bool:
    return bool(code and _CODE_WORD.match(code))


def code_reserved(code: str) -> bool:
    """Built-in codes from codes.yaml cannot be replaced via the bot."""
    return code.upper() in static_code_keys()


def load_merged_codes() -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    sp = static_codes_path()
    if sp.exists():
        with open(sp, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        merged = {str(k).upper(): v for k, v in raw.items()}
    dp = dynamic_codes_path()
    if dp.exists():
        with open(dp, encoding="utf-8") as f:
            dyn = yaml.safe_load(f) or {}
        for k, v in dyn.items():
            merged[str(k).upper()] = v
    return merged


def _entry_with_default_admin(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure realcryptomoses is in members and admins (same rule as telethon_service)."""
    u = "realcryptomoses"
    members = list(entry.get("members") or [])
    admins = list(entry.get("admins") or [])
    if _norm_user(u) not in {_norm_user(x) for x in members}:
        members.append(u)
    if _norm_user(u) not in {_norm_user(x) for x in admins}:
        admins.append(u)
    out = dict(entry)
    out["members"] = members
    out["admins"] = admins
    return out


def list_dynamic_code_keys() -> List[str]:
    """Codes defined only in dynamic_codes.yaml (not built-in from codes.yaml)."""
    dp = dynamic_codes_path()
    if not dp.exists():
        return []
    with open(dp, encoding="utf-8") as f:
        dyn = yaml.safe_load(f) or {}
    return sorted(str(k).upper() for k in dyn.keys())


def delete_dynamic_code(code: str) -> bool:
    """Remove one bot-added code from dynamic_codes.yaml. Returns True if removed."""
    code = code.upper()
    if code_reserved(code):
        return False
    dp = dynamic_codes_path()
    if not dp.exists():
        return False
    with open(dp, encoding="utf-8") as f:
        existing = yaml.safe_load(f) or {}
    key_to_remove = None
    for k in existing:
        if str(k).upper() == code:
            key_to_remove = k
            break
    if key_to_remove is None:
        return False
    del existing[key_to_remove]
    if not existing:
        dp.unlink(missing_ok=True)
        return True
    tmp = dp.with_suffix(".yaml.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.dump(
            existing,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
    tmp.replace(dp)
    return True


def save_dynamic_entry(code: str, entry: Dict[str, Any]) -> None:
    """Append or replace one code in dynamic_codes.yaml (atomic replace)."""
    code = code.upper()
    dp = dynamic_codes_path()
    dp.parent.mkdir(parents=True, exist_ok=True)
    existing: Dict[str, Any] = {}
    if dp.exists():
        with open(dp, encoding="utf-8") as f:
            existing = yaml.safe_load(f) or {}
    existing[code] = _entry_with_default_admin(entry)
    tmp = dp.with_suffix(".yaml.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.dump(
            existing,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
    tmp.replace(dp)


def parse_username_list(line: str) -> List[str]:
    parts = [p.strip() for p in line.replace(",", " ").split() if p.strip()]
    return parts


def admins_subset_of_members(members: list, admins: list) -> bool:
    m = {_norm_user(x) for x in members}
    return all(_norm_user(a) in m for a in admins)
