"""Character profiles in YAML: loading, validation and conversion to SpeakEasy data."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import speakeasy as se
from .issues import Issue, Report, Scope
from .luadata import as_list
from .scenes import Scene, Trigger, Wheel, derive_id, nbytes

__all__ = ["Issue", "Profile", "ProfileLoader", "derive_id", "from_set", "load", "nbytes", "yaml_files"]

PROFILE_KEYS = {"character", "target", "use_own", "settings", "scenes", "triggers", "wheel", "preview"}
CHARACTER_KEYS = {"name", "realm", "account"}
TARGETS = ("character", "account")
TRIGGER_CONTEXT_EVENTS = ("SPELL_CAST", "EAT_DRINK")


@dataclass
class Profile:
    """One character's validated scenes, possibly gathered from several YAML files."""

    sources: list[Path] = field(default_factory=list)
    character: dict[str, Any] = field(default_factory=dict)
    target: str = "character"
    use_own: bool = True
    settings: dict[str, Any] = field(default_factory=dict)
    scenes: list[Scene] = field(default_factory=list)
    triggers: list[Trigger] = field(default_factory=list)
    wheel: Wheel | None = None
    preview: dict[str, Any] = field(default_factory=dict)
    report: Report = field(default_factory=Report)

    @property
    def issues(self) -> list[Issue]:
        """Every error and warning, in the order found."""
        return self.report.issues

    @property
    def errors(self) -> list[Issue]:
        """Problems that stop the profile from being applied."""
        return self.report.errors

    @property
    def warnings(self) -> list[Issue]:
        """Problems worth a look that do not block applying."""
        return self.report.warnings

    @property
    def is_account(self) -> bool:
        """Whether the scenes go to the shared (account) file."""
        return self.target == "account"

    def scene_id(self, ref: Any) -> str | None:
        """Return the id of the scene whose id or name is ``ref``."""
        for scene in self.scenes:
            if ref in (scene.id, scene.name):
                return scene.id
        return None

    def scene_names(self) -> dict[str, str]:
        """Map scene ids to their display names."""
        return {scene.id: scene.name for scene in self.scenes}

    def to_set(self) -> dict[str, Any]:
        """Return SpeakEasy's ``{scenes, triggers, wheelPages}`` for this profile."""
        data: dict[str, Any] = {
            "scenes": [scene.to_speakeasy() for scene in self.scenes],
            "triggers": [trigger.to_speakeasy() for trigger in self.triggers],
        }
        if self.wheel is not None:
            data["wheelPages"] = self.wheel.to_speakeasy()
        return data


@dataclass
class _Draft:
    """Raw YAML gathered from every file of a profile, before validation."""

    sources: list[Path] = field(default_factory=list)
    character: dict[str, Any] = field(default_factory=dict)
    target: Any = "character"
    use_own: Any = True
    settings: dict[str, Any] = field(default_factory=dict)
    preview: dict[str, Any] = field(default_factory=dict)
    scenes: list[tuple[Scope, Any]] = field(default_factory=list)
    triggers: list[tuple[Scope, Any]] = field(default_factory=list)
    wheel: Any = None


def yaml_files(paths: list[Path]) -> list[Path]:
    """Expand folders into the ``.yaml``/``.yml`` files inside them, sorted."""
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(p for p in path.rglob("*") if p.suffix in (".yaml", ".yml")))
        else:
            files.append(path)
    return files


class ProfileLoader:
    """Reads the YAML files of one profile, merges them and validates the result."""

    def __init__(self) -> None:
        """Start with an empty profile and no issues."""
        self.report = Report()
        self.draft = _Draft()

    def load(self, paths: list[str | Path]) -> Profile:
        """Read files (or folders of them) and return the validated profile."""
        for path in yaml_files([Path(p) for p in paths]):
            self._read(path)
        if not self.draft.sources:
            self.report.at("input").error("no YAML files found")
        return _ProfileBuilder(self.draft, self.report).build()

    def _read(self, path: Path) -> None:
        self.draft.sources.append(path)
        scope = self.report.at(str(path))
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            scope.error(f"cannot read YAML: {exc}")
            return
        if data is None:
            return
        if not isinstance(data, dict):
            scope.error("the file must be a mapping (key: value) at the top level")
            return
        self._merge(scope, data)

    def _merge(self, scope: Scope, data: dict[str, Any]) -> None:
        for key in data:
            if key not in PROFILE_KEYS:
                scope.error(f"unknown key '{key}' (allowed: {', '.join(sorted(PROFILE_KEYS))})")
        self._merge_character(scope, data.get("character"))
        for key in ("target", "use_own"):
            if key in data:
                setattr(self.draft, key, data[key])
        for key in ("settings", "preview"):
            self._merge_mapping(scope, key, data.get(key))
        self._merge_items(scope, "scenes", data.get("scenes"), self.draft.scenes)
        self._merge_items(scope, "triggers", data.get("triggers"), self.draft.triggers)
        if "wheel" in data:
            if self.draft.wheel is not None:
                scope.error("'wheel' is already set in another file; keep it in one place")
            self.draft.wheel = data["wheel"]

    def _merge_character(self, scope: Scope, character: Any) -> None:
        if character is None:
            return
        if not isinstance(character, dict):
            scope.error("'character' must be a mapping")
            return
        for key, value in character.items():
            if key in self.draft.character and self.draft.character[key] != value:
                scope.error(f"character.{key} differs from an earlier file")
            self.draft.character[key] = value

    def _merge_mapping(self, scope: Scope, key: str, value: Any) -> None:
        if value is None:
            return
        if not isinstance(value, dict):
            scope.error(f"'{key}' must be a mapping")
            return
        getattr(self.draft, key).update(value)

    @staticmethod
    def _merge_items(scope: Scope, key: str, value: Any, into: list[tuple[Scope, Any]]) -> None:
        if value is None:
            return
        if not isinstance(value, list):
            scope.error(f"'{key}' must be a list")
            return
        into.extend((scope.child(f": {key}[{index}]"), item) for index, item in enumerate(value, start=1))


class _ProfileBuilder:
    """Validates a draft and turns it into a :class:`Profile`."""

    def __init__(self, draft: _Draft, report: Report) -> None:
        self.draft = draft
        self.report = report

    def build(self) -> Profile:
        draft = self.draft
        profile = Profile(
            sources=draft.sources,
            character=draft.character,
            target=str(draft.target),
            use_own=self.report.at("use_own").flag(draft.use_own, "use_own"),
            settings=draft.settings,
            preview=draft.preview,
            report=self.report,
        )
        self._check_character(profile)
        self._check_settings(profile.settings)
        taken: set[str] = set()
        profile.scenes = [scene for scope, raw in draft.scenes if (scene := Scene.parse(raw, scope, taken))]
        profile.triggers = [trigger for scope, raw in draft.triggers if (trigger := Trigger.parse(raw, scope, profile.scene_id))]
        if draft.wheel is not None:
            profile.wheel = Wheel.parse(draft.wheel, self.report.at("wheel"), profile.scene_id)
        self._check_trigger_variables(profile)
        return profile

    def _check_character(self, profile: Profile) -> None:
        scope = self.report.at("character")
        for key in sorted(CHARACTER_KEYS):
            value = profile.character.get(key)
            if value is not None and not isinstance(value, str):
                scope.error(f"character.{key} must be text")
        if profile.target not in TARGETS:
            self.report.at("target").error("target must be 'character' or 'account'")
        if profile.target == "character" and not (profile.character.get("name") and profile.character.get("realm")):
            scope.error("character.name and character.realm are needed to find the character's file")

    def _check_settings(self, settings: dict[str, Any]) -> None:
        scope = self.report.at("settings")
        for key, value in settings.items():
            if key not in se.SETTINGS_DEFAULT:
                scope.error(f"unknown SpeakEasy setting '{key}'")
            elif not _same_kind(value, se.SETTINGS_DEFAULT[key]):
                scope.error(f"{key} must be like {se.SETTINGS_DEFAULT[key]!r}")
            elif key in se.SETTINGS_RANGES:
                scope.number(value, key, se.SETTINGS_RANGES[key], value)

    @staticmethod
    def _check_trigger_variables(profile: Profile) -> None:
        context_scenes = {t.scene_id for t in profile.triggers if t.event in TRIGGER_CONTEXT_EVENTS}
        for scene in profile.scenes:
            if scene.id in context_scenes:
                continue
            for line in scene.lines:
                used = line.variables & se.TRIGGER_ONLY_VARIABLES
                if used:
                    names = ", ".join(sorted("{" + u + "}" for u in used))
                    profile.report.at(scene.where).warn(f"{names} is only filled by SPELL_CAST or EAT_DRINK triggers")


def _same_kind(value: Any, default: Any) -> bool:
    """Whether ``value`` has the type of ``default``, treating int and float alike."""
    if type(value) is type(default):
        return True
    numbers = (int, float)
    return isinstance(default, numbers) and isinstance(value, numbers) and not isinstance(value, bool)


def load(paths: list[str | Path]) -> Profile:
    """Read YAML files (or folders of them) into one validated profile."""
    return ProfileLoader().load(paths)


def from_set(data: dict[str, Any], character: dict[str, Any] | None = None, target: str = "character") -> dict[str, Any]:
    """Turn a SpeakEasy set back into profile YAML data (for export)."""
    result: dict[str, Any] = {}
    if character:
        result["character"] = character
    result["target"] = target
    result["scenes"] = [Scene.from_speakeasy(scene).to_yaml() for scene in as_list(data.get("scenes")) if isinstance(scene, dict)]
    result["triggers"] = [Trigger.from_speakeasy(trigger).to_yaml() for trigger in as_list(data.get("triggers")) if isinstance(trigger, dict)]
    pages = as_list(data.get("wheelPages"))
    if pages:
        result["wheel"] = [as_list(page) for page in pages]
    return result
