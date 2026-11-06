"""Find SpeakEasy's SavedVariables files and merge a profile into them."""

from __future__ import annotations

import copy
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from . import luadata
from . import speakeasy as se
from .luadata import as_list, as_table
from .model import Profile

FILE_NAME = "SpeakEasy.lua"
ACCOUNT_VAR = "SpeakEasyDB"
CHARACTER_VAR = "SpeakEasyCharDB"


class PathError(ValueError):
    """Raised when the WTF folder, an account, realm or character cannot be found."""


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
    """Return the account folders under ``WTF/Account``."""
    return sorted(p for p in (wtf / "Account").iterdir() if p.is_dir() and p.name != "SavedVariables")


def account_dir(wtf: Path, account: str | None) -> Path:
    """Find an account folder by name (any case), or the only one when ``account`` is empty."""
    if account:
        return _child(wtf / "Account", account, "account")
    found = accounts(wtf)
    if len(found) != 1:
        names = ", ".join(p.name for p in found) or "none"
        raise PathError(f"choose an account with --account or character.account (found: {names})")
    return found[0]


def account_file(wtf: Path, account: str | None) -> Path:
    """Return the shared ``SpeakEasy.lua`` of an account."""
    return account_dir(wtf, account) / "SavedVariables" / FILE_NAME


def character_file(wtf: Path, account: str | None, realm: str, name: str) -> Path:
    """Return a character's ``SpeakEasy.lua``; realm and name match in any case."""
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


@dataclass(frozen=True)
class SavedVariablesFile:
    """One ``SpeakEasy.lua`` and the global (``SpeakEasyDB`` or ``SpeakEasyCharDB``) it holds."""

    path: Path
    variable: str

    def read(self) -> dict[str, Any] | None:
        """Return the stored table, or ``None`` when the file or the table is missing."""
        if not self.path.exists():
            return None
        value = luadata.loads(self.path.read_bytes()).get(self.variable)
        return value if isinstance(value, dict) else None

    def write(self, data: dict[str, Any]) -> Path | None:
        """Write the file, keeping a timestamped backup of the old one; return the backup."""
        backup = None
        if self.path.exists():
            backup = self.path.with_name(f"{self.path.name}.{datetime.now():%Y%m%d-%H%M%S}.bak")
            shutil.copy2(self.path, backup)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = luadata.dumps({self.variable: data})
        self.path.write_bytes(text.encode("utf-8", errors="surrogateescape"))
        return backup


def read(path: Path, variable: str) -> dict[str, Any] | None:
    """Return ``variable`` from the file at ``path``, if both exist."""
    return SavedVariablesFile(path, variable).read()


@dataclass
class Change:
    """What a merge did, for the apply report."""

    added: list[str] = field(default_factory=list)
    replaced: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    triggers_removed: int = 0
    triggers_added: int = 0
    wheel: bool = False


def _trigger_key(trigger: dict[str, Any]) -> tuple[Any, ...]:
    options = as_table(trigger.get("options"))
    spells = tuple(sorted(str(s.get("spell", "")).lower() for s in as_list(options.get("spells")) if isinstance(s, dict)))
    return trigger.get("event"), trigger.get("sceneId"), options.get("threshold"), spells


class SetMerger:
    """Merges a profile's set into stored SpeakEasy data.

    Scenes are matched by id; stored triggers for those scenes (or identical to an
    incoming one) are replaced; the wheel is replaced only when the profile has one.
    With ``replace``, everything stored is dropped first.
    """

    def __init__(self, replace: bool = False) -> None:
        """Choose between merging (default) and replacing stored scenes."""
        self.replace = replace

    def merge(self, existing: dict[str, Any] | None, incoming: dict[str, Any]) -> tuple[dict[str, Any], Change]:
        """Return the merged copy of ``existing`` and what changed; ``existing`` is untouched."""
        result = copy.deepcopy(existing) if existing else {}
        change = Change(triggers_added=len(incoming["triggers"]), wheel="wheelPages" in incoming)
        result["scenes"] = self._scenes(as_list(result.get("scenes")), incoming["scenes"], change)
        result["triggers"] = self._triggers(as_list(result.get("triggers")), incoming, change)
        if "wheelPages" in incoming:
            result["wheelPages"] = incoming["wheelPages"]
        elif self.replace:
            result.pop("wheelPages", None)
        return result, change

    def _scenes(self, stored: list[Any], incoming: list[dict[str, Any]], change: Change) -> list[Any]:
        pending = {scene["id"]: scene for scene in incoming}
        scenes = []
        for scene in [] if self.replace else stored:
            scene_id = scene.get("id") if isinstance(scene, dict) else None
            if isinstance(scene_id, str) and scene_id in pending:
                scenes.append(pending.pop(scene_id))
                change.replaced.append(scene_id)
            else:
                scenes.append(scene)
                change.kept.append(str(scene_id))
        change.added = [scene["id"] for scene in incoming if scene["id"] in pending]
        scenes.extend(pending[scene_id] for scene_id in change.added)
        return scenes

    def _triggers(self, stored: list[Any], incoming: dict[str, Any], change: Change) -> list[Any]:
        old = [] if self.replace else stored
        scene_ids = {scene["id"] for scene in incoming["scenes"]}
        keys = {_trigger_key(trigger) for trigger in incoming["triggers"]}
        survivors = [t for t in old if isinstance(t, dict) and t.get("sceneId") not in scene_ids and _trigger_key(t) not in keys]
        change.triggers_removed = len(old) - len(survivors)
        return survivors + list(incoming["triggers"])


def merge(existing: dict[str, Any] | None, incoming: dict[str, Any], replace: bool = False) -> tuple[dict[str, Any], Change]:
    """Merge a set into stored data: scenes by id, triggers for those scenes, the wheel if given."""
    return SetMerger(replace).merge(existing, incoming)


@dataclass
class Plan:
    """Everything ``apply`` would write: the scenes file and, optionally, account settings."""

    file: SavedVariablesFile
    data: dict[str, Any]
    change: Change
    settings_file: SavedVariablesFile | None = None
    settings_data: dict[str, Any] | None = None


def _target_file(profile: Profile, wtf: Path | None, out: Path | None, account: str | None) -> SavedVariablesFile:
    variable = ACCOUNT_VAR if profile.is_account else CHARACTER_VAR
    if out is not None:
        return SavedVariablesFile(out, variable)
    if wtf is None:
        raise PathError("set --game-dir (or SPEAKEASY_GAME_DIR) or give --out")
    if profile.is_account:
        return SavedVariablesFile(account_file(wtf, account), variable)
    character = profile.character
    return SavedVariablesFile(character_file(wtf, account, character["realm"], character["name"]), variable)


def _account_settings(settings: dict[str, Any], wtf: Path, account: str | None) -> tuple[SavedVariablesFile, dict[str, Any]]:
    target = SavedVariablesFile(account_file(wtf, account), ACCOUNT_VAR)
    stored = target.read()
    if stored is None:
        raise PathError("settings: log in once with SpeakEasy enabled so its account file exists")
    stored.setdefault("settings", {}).update(settings)
    return target, stored


def plan(profile: Profile, wtf: Path | None, out: Path | None = None, account: str | None = None, replace: bool = False) -> Plan:
    """Work out what applying a profile would write, without touching any file."""
    account = account or profile.character.get("account")
    target = _target_file(profile, wtf, out, account)
    data, change = SetMerger(replace).merge(target.read(), profile.to_set())
    result = Plan(target, data, change)
    if profile.is_account:
        data["version"] = se.DB_VERSION
        if profile.settings:
            data.setdefault("settings", {}).update(profile.settings)
    else:
        data["useOwn"] = profile.use_own
        if profile.settings and wtf is not None and out is None:
            result.settings_file, result.settings_data = _account_settings(profile.settings, wtf, account)
    return result


def apply(result: Plan) -> list[Path]:
    """Write a plan's files and return the backups made."""
    backups = [result.file.write(result.data)]
    if result.settings_file and result.settings_data is not None:
        backups.append(result.settings_file.write(result.settings_data))
    return [b for b in backups if b]
