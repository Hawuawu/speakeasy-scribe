"""Find SpeakEasy's SavedVariables files and merge a profile into them."""

from __future__ import annotations

import copy
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from . import luadata
from . import speakeasy as se
from .model import Profile, to_set

FILE_NAME = "SpeakEasy.lua"
ACCOUNT_VAR = "SpeakEasyDB"
CHARACTER_VAR = "SpeakEasyCharDB"


class PathError(ValueError):
    pass


def wtf_dir(game_dir: str | Path) -> Path:
    """Accept the client folder (holding WTF) or the WTF folder itself."""
    path = Path(game_dir).expanduser()
    for candidate in (path, path / "WTF"):
        if candidate.name.upper() == "WTF" and (candidate / "Account").is_dir():
            return candidate
    raise PathError(f"no WTF/Account folder under {path}; point --game-dir at the folder with WTF and Interface")


def _child(parent: Path, name: str, what: str) -> Path:
    if parent.is_dir():
        for child in parent.iterdir():
            if child.is_dir() and child.name.lower() == name.lower():
                return child
    raise PathError(f"{what} '{name}' not found in {parent}")


def accounts(wtf: Path) -> list[Path]:
    return sorted(p for p in (wtf / "Account").iterdir() if p.is_dir() and p.name != "SavedVariables")


def account_dir(wtf: Path, account: str | None) -> Path:
    if account:
        return _child(wtf / "Account", account, "account")
    found = accounts(wtf)
    if len(found) != 1:
        names = ", ".join(p.name for p in found) or "none"
        raise PathError(f"choose an account with --account or character.account (found: {names})")
    return found[0]


def account_file(wtf: Path, account: str | None) -> Path:
    return account_dir(wtf, account) / "SavedVariables" / FILE_NAME


def character_file(wtf: Path, account: str | None, realm: str, name: str) -> Path:
    realm_dir = _child(account_dir(wtf, account), realm, "realm")
    return _child(realm_dir, name, "character") / "SavedVariables" / FILE_NAME


def characters(wtf: Path) -> list[tuple[str, str, str, Path]]:
    """(account, realm, character, SpeakEasy.lua path) for every character folder."""
    found = []
    for account in accounts(wtf):
        for realm in sorted(p for p in account.iterdir() if p.is_dir() and p.name != "SavedVariables"):
            for char in sorted(p for p in realm.iterdir() if p.is_dir()):
                found.append((account.name, realm.name, char.name, char / "SavedVariables" / FILE_NAME))
    return found


def read(path: Path, variable: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    value = luadata.loads(path.read_bytes()).get(variable)
    return value if isinstance(value, dict) else None


def write(path: Path, variable: str, data: dict[str, Any]) -> Path | None:
    """Write the file, keeping a timestamped backup of the old one."""
    backup = None
    if path.exists():
        backup = path.with_name(f"{path.name}.{datetime.now():%Y%m%d-%H%M%S}.bak")
        shutil.copy2(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = luadata.dumps({variable: data})
    path.write_bytes(text.encode("utf-8", errors="surrogateescape"))
    return backup


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and not value:
        return []
    if isinstance(value, dict):
        return [value[k] for k in sorted(k for k in value if isinstance(k, int))]
    return []


def _trigger_key(trigger: dict[str, Any]) -> tuple[Any, ...]:
    options = trigger.get("options") or {}
    spells = tuple(sorted(str(s.get("spell", "")).lower() for s in _as_list(options.get("spells"))))
    return trigger.get("event"), trigger.get("sceneId"), options.get("threshold"), spells


@dataclass
class Change:
    added: list[str]
    replaced: list[str]
    kept: list[str]
    triggers_removed: int
    triggers_added: int
    wheel: bool


def merge(existing: dict[str, Any] | None, incoming: dict[str, Any], replace: bool = False) -> tuple[dict[str, Any], Change]:
    """Merge a set into stored data: scenes by id, triggers for those scenes, the wheel if given."""
    result = copy.deepcopy(existing) if existing else {}
    old_scenes = [] if replace else _as_list(result.get("scenes"))
    new_ids = [scene["id"] for scene in incoming["scenes"]]
    by_id = {scene["id"]: scene for scene in incoming["scenes"]}
    scenes, replaced, kept = [], [], []
    for scene in old_scenes:
        scene_id = scene.get("id") if isinstance(scene, dict) else None
        if scene_id in by_id:
            scenes.append(by_id.pop(scene_id))
            replaced.append(scene_id)
        else:
            scenes.append(scene)
            kept.append(str(scene_id))
    added = [scene_id for scene_id in new_ids if scene_id in by_id]
    scenes.extend(by_id[scene_id] for scene_id in added)

    old_triggers = [] if replace else _as_list(result.get("triggers"))
    incoming_keys = {_trigger_key(t) for t in incoming["triggers"]}
    survivors = [t for t in old_triggers if isinstance(t, dict) and t.get("sceneId") not in new_ids and _trigger_key(t) not in incoming_keys]
    result["scenes"] = scenes
    result["triggers"] = survivors + list(incoming["triggers"])
    if "wheelPages" in incoming:
        result["wheelPages"] = incoming["wheelPages"]
    elif replace:
        result.pop("wheelPages", None)
    change = Change(added, replaced, kept, len(old_triggers) - len(survivors), len(incoming["triggers"]), "wheelPages" in incoming)
    return result, change


@dataclass
class Plan:
    path: Path
    variable: str
    data: dict[str, Any]
    change: Change
    settings_path: Path | None = None
    settings_data: dict[str, Any] | None = None


def plan(profile: Profile, wtf: Path | None, out: Path | None = None, account: str | None = None, replace: bool = False) -> Plan:
    """Work out what applying a profile would write, without touching any file."""
    character = profile.character
    account = account or character.get("account")
    is_account = profile.target == "account"
    variable = ACCOUNT_VAR if is_account else CHARACTER_VAR
    if out is not None:
        path = out
    elif wtf is None:
        raise PathError("set --game-dir (or SPEAKEASY_GAME_DIR) or give --out")
    elif is_account:
        path = account_file(wtf, account)
    else:
        path = character_file(wtf, account, character["realm"], character["name"])
    existing = read(path, variable)
    data, change = merge(existing, to_set(profile), replace)
    if is_account:
        data["version"] = se.DB_VERSION
    else:
        data["useOwn"] = profile.use_own

    result = Plan(path, variable, data, change)
    if profile.settings:
        if is_account:
            data.setdefault("settings", {}).update(profile.settings)
        elif wtf is not None and out is None:
            settings_path = account_file(wtf, account)
            stored = read(settings_path, ACCOUNT_VAR)
            if stored is None:
                raise PathError("settings: log in once with SpeakEasy enabled so its account file exists")
            stored.setdefault("settings", {}).update(profile.settings)
            result.settings_path, result.settings_data = settings_path, stored
    return result


def apply(result: Plan) -> list[Path]:
    backups = [write(result.path, result.variable, result.data)]
    if result.settings_path and result.settings_data is not None:
        backups.append(write(result.settings_path, ACCOUNT_VAR, result.settings_data))
    return [b for b in backups if b]
