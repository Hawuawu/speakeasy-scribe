"""Character profiles in YAML: loading, validation and conversion to SpeakEasy data."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import speakeasy as se

PROFILE_KEYS = {"character", "target", "use_own", "settings", "scenes", "triggers", "wheel", "preview"}
CHARACTER_KEYS = {"name", "realm", "account"}
SCENE_KEYS = {"id", "name", "channel", "icon", "cooldown", "emote", "enabled", "macro_name", "lines", "notes"}
LINE_KEYS = {"text", "emote", "enabled"}
TRIGGER_KEYS = {"event", "scene", "chance", "cooldown", "enabled", "threshold", "spells"}
TARGETS = ("character", "account")
_ID = re.compile(r"^[a-z0-9]+$")
_EMOTE = re.compile(r"^[A-Z0-9_]+$")
_VARIABLE = re.compile(r"\{(\w+)\}")


@dataclass
class Issue:
    level: str  # "error" or "warning"
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.level}: {self.where}: {self.message}"


@dataclass
class Profile:
    """One character's scenes, possibly gathered from several YAML files."""

    sources: list[Path] = field(default_factory=list)
    character: dict[str, Any] = field(default_factory=dict)
    target: str = "character"
    use_own: bool = True
    settings: dict[str, Any] = field(default_factory=dict)
    scenes: list[dict[str, Any]] = field(default_factory=list)
    triggers: list[dict[str, Any]] = field(default_factory=list)
    wheel: list[Any] | None = None
    preview: dict[str, Any] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.level == "warning"]

    def error(self, where: str, message: str) -> None:
        self.issues.append(Issue("error", where, message))

    def warn(self, where: str, message: str) -> None:
        self.issues.append(Issue("warning", where, message))


def nbytes(text: str) -> int:
    return len(text.encode("utf-8", errors="surrogateescape"))


def derive_id(name: str) -> str:
    """Same rule as SpeakEasy: lower case, letters and digits only."""
    return re.sub(r"[^0-9a-z]", "", str(name).lower()) or "scene"


def yaml_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(p for p in path.rglob("*") if p.suffix in (".yaml", ".yml")))
        else:
            files.append(path)
    return files


def load(paths: list[str | Path]) -> Profile:
    """Read YAML files (or folders of them) into one validated profile."""
    profile = Profile()
    for path in yaml_files([Path(p) for p in paths]):
        profile.sources.append(path)
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            profile.error(str(path), f"cannot read YAML: {exc}")
            continue
        if data is None:
            continue
        if not isinstance(data, dict):
            profile.error(str(path), "the file must be a mapping (key: value) at the top level")
            continue
        _merge_file(profile, path, data)
    if not profile.sources:
        profile.error("input", "no YAML files found")
    validate(profile)
    return profile


def _merge_file(profile: Profile, path: Path, data: dict[str, Any]) -> None:
    where = str(path)
    for key in data:
        if key not in PROFILE_KEYS:
            profile.error(where, f"unknown key '{key}' (allowed: {', '.join(sorted(PROFILE_KEYS))})")
    character = data.get("character")
    if character is not None:
        if not isinstance(character, dict):
            profile.error(where, "'character' must be a mapping")
        else:
            for key, value in character.items():
                if key in profile.character and profile.character[key] != value:
                    profile.error(where, f"character.{key} differs from an earlier file")
                profile.character[key] = value
    for key in ("target", "use_own"):
        if key in data:
            setattr(profile, key, data[key])
    for key in ("settings", "preview"):
        value = data.get(key)
        if value is not None:
            if isinstance(value, dict):
                getattr(profile, key).update(value)
            else:
                profile.error(where, f"'{key}' must be a mapping")
    for key in ("scenes", "triggers"):
        value = data.get(key)
        if value is None:
            continue
        if not isinstance(value, list):
            profile.error(where, f"'{key}' must be a list")
            continue
        for index, item in enumerate(value, start=1):
            getattr(profile, key).append({"_where": f"{where}: {key}[{index}]", "_raw": item})
    if "wheel" in data:
        if profile.wheel is not None:
            profile.error(where, "'wheel' is already set in another file; keep it in one place")
        profile.wheel = data["wheel"]


def _number(profile: Profile, where: str, value: Any, name: str, bounds: tuple[float, float], default: float) -> float:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        profile.error(where, f"{name} must be a number")
        return default
    low, high = bounds
    if not low <= value <= high:
        profile.error(where, f"{name} must be between {low} and {high}")
    return value


def _check_text(profile: Profile, where: str, text: str) -> None:
    if "\n" in text or "\r" in text:
        profile.error(where, "a line cannot contain a line break; split it into two lines")
    if "|" in text:
        profile.error(where, "'|' starts a WoW escape code and breaks chat; remove it")
    if nbytes(text) > se.MAX_LINE_BYTES:
        profile.error(where, f"line is {nbytes(text)} bytes; SpeakEasy cuts lines at {se.MAX_LINE_BYTES}")
    for name in _VARIABLE.findall(text):
        if name not in se.VARIABLES:
            profile.warn(where, f"unknown variable {{{name}}} is sent as typed")


def _check_emote(profile: Profile, where: str, emote: Any) -> str | None:
    if emote is None or emote == "":
        return None
    if not isinstance(emote, str) or not _EMOTE.match(emote) or nbytes(emote) > se.MAX_EMOTE_BYTES:
        profile.error(where, f"emote {emote!r} must be an upper-case emote token such as BOW or WAVE")
        return None
    return emote


def _line(profile: Profile, where: str, raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, str):
        raw = {"text": raw}
    if isinstance(raw, dict) and not set(raw) <= LINE_KEYS:
        profile.error(where, "a line starting with '{' must be quoted, or use text:/emote:/enabled: keys")
        return None
    if not isinstance(raw, dict):
        profile.error(where, f"line must be text in quotes, got {type(raw).__name__} {raw!r}")
        return None
    text = raw.get("text") or ""
    if not isinstance(text, str):
        profile.error(where, "text must be a quoted string")
        return None
    _check_text(profile, where, text)
    emote = _check_emote(profile, where, raw.get("emote"))
    if not text.strip() and not emote:
        profile.error(where, "line has neither text nor an emote")
        return None
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        profile.error(where, "enabled must be true or false")
    line = {"text": text, "emote": emote, "enabled": enabled is not False}
    return {k: v for k, v in line.items() if v is not None}


def _scene(profile: Profile, entry: dict[str, Any], taken: set[str]) -> None:
    where, raw = entry["_where"], entry["_raw"]
    entry.clear()
    entry["_where"] = where
    if not isinstance(raw, dict):
        profile.error(where, "scene must be a mapping")
        return
    for key in raw:
        if key not in SCENE_KEYS:
            profile.error(where, f"unknown scene key '{key}'")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        profile.error(where, "scene needs a name")
        return
    where = f"{where} '{name}'"
    entry["_where"] = where
    if nbytes(name) > se.MAX_NAME_BYTES:
        profile.error(where, f"name is longer than {se.MAX_NAME_BYTES} bytes")
    scene_id = raw.get("id", derive_id(name))
    if not isinstance(scene_id, str) or not _ID.match(scene_id):
        profile.error(where, "id must be lower-case letters and digits only")
    elif scene_id in se.RESERVED_IDS:
        profile.error(where, f"id '{scene_id}' is reserved by /speakeasy")
    elif scene_id in taken:
        profile.error(where, f"id '{scene_id}' is used by another scene; set a different id")
    taken.add(str(scene_id))
    channel = raw.get("channel", "SAY")
    if channel not in se.CHANNELS:
        profile.error(where, f"channel must be one of {', '.join(se.CHANNELS)}")
    icon = raw.get("icon", se.DEFAULT_ICON)
    if isinstance(icon, bool) or not isinstance(icon, int):
        profile.error(where, "icon must be a texture file ID (a whole number)")
        icon = se.DEFAULT_ICON
    cooldown = _number(profile, where, raw.get("cooldown"), "cooldown", se.COOLDOWN_RANGE, 2)
    macro = raw.get("macro_name")
    if macro is not None and (not isinstance(macro, str) or nbytes(macro) > se.MAX_MACRO_NAME_BYTES):
        profile.error(where, f"macro_name must be text of at most {se.MAX_MACRO_NAME_BYTES} bytes")
    lines_raw = raw.get("lines") or []
    if not isinstance(lines_raw, list):
        profile.error(where, "lines must be a list")
        lines_raw = []
    lines = []
    for index, line in enumerate(lines_raw, start=1):
        clean = _line(profile, f"{where} line {index}", line)
        if clean:
            lines.append(clean)
    if not any(line["enabled"] for line in lines):
        profile.warn(where, "scene has no enabled lines")
    entry.update(
        id=scene_id,
        name=name.strip(),
        icon=icon,
        channel=channel,
        defaultEmote=_check_emote(profile, where, raw.get("emote")),
        cooldown=cooldown,
        enabled=raw.get("enabled", True) is not False,
        macroName=macro,
        lines=lines,
    )


def _resolve(profile: Profile, ref: Any) -> str | None:
    for scene in profile.scenes:
        if ref == scene.get("id") or ref == scene.get("name"):
            return scene["id"]
    return None


def _trigger(profile: Profile, entry: dict[str, Any]) -> None:
    where, raw = entry["_where"], entry["_raw"]
    entry.clear()
    entry["_where"] = where
    if not isinstance(raw, dict):
        profile.error(where, "trigger must be a mapping")
        return
    for key in raw:
        if key not in TRIGGER_KEYS:
            profile.error(where, f"unknown trigger key '{key}'")
    event = raw.get("event")
    if event not in se.EVENTS:
        profile.error(where, f"event must be one of {', '.join(se.EVENTS)}; SpeakEasy has no other triggers")
        return
    ref = raw.get("scene")
    scene_id = _resolve(profile, ref)
    if scene_id is None:
        if isinstance(ref, str) and _ID.match(ref):
            scene_id = ref
            profile.warn(where, f"scene '{ref}' is not in this profile; it must already exist in SpeakEasy")
        else:
            profile.error(where, f"scene {ref!r} not found")
            return
    options: dict[str, Any] = {}
    if "threshold" in raw and event != "LOW_HEALTH":
        profile.warn(where, "threshold only matters for LOW_HEALTH")
    # SpeakEasy stores a threshold on every trigger; writing it keeps files identical after its clean-up.
    options["threshold"] = _number(profile, where, raw.get("threshold"), "threshold", se.THRESHOLD_RANGE, 30)
    if event == "SPELL_CAST":
        spells = []
        for spell in raw.get("spells") or []:
            if isinstance(spell, str):
                spell = {"spell": spell}
            if not isinstance(spell, dict) or not isinstance(spell.get("spell"), str) or not spell["spell"].strip():
                profile.error(where, "each spell must be a name, or spell:/item: keys")
                continue
            if any(nbytes(str(v)) > se.MAX_SPELL_BYTES for v in spell.values()):
                profile.error(where, f"spell and item names are limited to {se.MAX_SPELL_BYTES} bytes")
            spells.append({k: spell[k] for k in ("spell", "item") if spell.get(k)})
        if not spells:
            profile.error(where, "SPELL_CAST needs a list of spells")
        if len(spells) > se.MAX_TRIGGER_SPELLS:
            profile.error(where, f"at most {se.MAX_TRIGGER_SPELLS} spells per trigger")
        options["spells"] = spells
    elif "spells" in raw:
        profile.error(where, "spells only apply to SPELL_CAST")
    entry.update(
        event=event,
        sceneId=scene_id,
        chance=_number(profile, where, raw.get("chance"), "chance", se.CHANCE_RANGE, 30),
        cooldown=_number(profile, where, raw.get("cooldown"), "cooldown", se.COOLDOWN_RANGE, 60),
        enabled=raw.get("enabled", True) is not False,
        options=options,
    )


def _wheel(profile: Profile) -> list[list[str]] | None:
    if profile.wheel is None:
        return None
    raw = profile.wheel
    pages = raw if isinstance(raw, list) and all(isinstance(p, list) for p in raw) else None
    if pages is None:
        profile.error("wheel", "wheel must be a list of pages, each a list of up to 8 slots")
        return None
    if not 1 <= len(pages) <= se.MAX_WHEEL_PAGES:
        profile.error("wheel", f"wheel needs 1 to {se.MAX_WHEEL_PAGES} pages")
    clean = []
    for number, page in enumerate(pages, start=1):
        where = f"wheel page {number}"
        if len(page) > se.WHEEL_SLOTS:
            profile.error(where, f"a page has {se.WHEEL_SLOTS} slots")
        slots = []
        for slot in page[: se.WHEEL_SLOTS]:
            if slot in (None, ""):
                slots.append("")
            elif isinstance(slot, str) and slot.startswith(se.EMOTE_SLOT_PREFIX):
                _check_emote(profile, where, slot[len(se.EMOTE_SLOT_PREFIX) :])
                slots.append(slot)
            elif _resolve(profile, slot):
                slots.append(_resolve(profile, slot))
            else:
                profile.error(where, f"slot {slot!r} is not a scene in this profile or emote:TOKEN")
                slots.append("")
        clean.append(slots + [""] * (se.WHEEL_SLOTS - len(slots)))
    return clean


def validate(profile: Profile) -> None:
    for key in profile.character:
        if key in CHARACTER_KEYS and profile.character[key] is not None and not isinstance(profile.character[key], str):
            profile.error("character", f"character.{key} must be text")
    if profile.target not in TARGETS:
        profile.error("target", "target must be 'character' or 'account'")
    if profile.target == "character" and not (profile.character.get("name") and profile.character.get("realm")):
        profile.error("character", "character.name and character.realm are needed to find the character's file")
    if not isinstance(profile.use_own, bool):
        profile.error("use_own", "use_own must be true or false")
    for key, value in profile.settings.items():
        if key not in se.SETTINGS_DEFAULT:
            profile.error("settings", f"unknown SpeakEasy setting '{key}'")
        elif type(value) is not type(se.SETTINGS_DEFAULT[key]) and not (
            isinstance(se.SETTINGS_DEFAULT[key], (int, float)) and isinstance(value, (int, float)) and not isinstance(value, bool)
        ):
            profile.error("settings", f"{key} must be like {se.SETTINGS_DEFAULT[key]!r}")
        elif key in se.SETTINGS_RANGES:
            _number(profile, "settings", value, key, se.SETTINGS_RANGES[key], value)
    taken: set[str] = set()
    for entry in profile.scenes:
        _scene(profile, entry, taken)
    profile.scenes = [s for s in profile.scenes if "id" in s]
    for entry in profile.triggers:
        _trigger(profile, entry)
    profile.triggers = [t for t in profile.triggers if "event" in t]
    profile.wheel = _wheel(profile)
    _check_trigger_variables(profile)


def _check_trigger_variables(profile: Profile) -> None:
    spell_scenes = {t["sceneId"] for t in profile.triggers if t["event"] in ("SPELL_CAST", "EAT_DRINK")}
    for scene in profile.scenes:
        for line in scene["lines"]:
            used = set(_VARIABLE.findall(line["text"])) & se.TRIGGER_ONLY_VARIABLES
            if used and scene["id"] not in spell_scenes:
                names = ", ".join(sorted("{" + u + "}" for u in used))
                profile.warn(scene["_where"], f"{names} is only filled by SPELL_CAST or EAT_DRINK triggers")


def _strip(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if not k.startswith("_") and v is not None}


def to_set(profile: Profile) -> dict[str, Any]:
    """SpeakEasy's {scenes, triggers, wheelPages} for this profile."""
    data: dict[str, Any] = {
        "scenes": [_strip(scene) for scene in profile.scenes],
        "triggers": [_strip(trigger) for trigger in profile.triggers],
    }
    if profile.wheel is not None:
        data["wheelPages"] = profile.wheel
    return data


def from_set(data: dict[str, Any], character: dict[str, Any] | None = None, target: str = "character") -> dict[str, Any]:
    """Turn a SpeakEasy set back into profile YAML data (for export)."""
    scenes = []
    for scene in _list(data.get("scenes")):
        lines = []
        for line in _list(scene.get("lines")):
            text, emote, enabled = line.get("text", ""), line.get("emote"), line.get("enabled", True)
            if emote or not enabled:
                item = {"text": text} if text else {}
                if emote:
                    item["emote"] = emote
                if not enabled:
                    item["enabled"] = False
                lines.append(item)
            else:
                lines.append(text)
        out = {"id": scene.get("id"), "name": scene.get("name"), "channel": scene.get("channel", "SAY")}
        if scene.get("icon", se.DEFAULT_ICON) != se.DEFAULT_ICON:
            out["icon"] = scene["icon"]
        if scene.get("cooldown", 2) != 2:
            out["cooldown"] = scene["cooldown"]
        if scene.get("defaultEmote"):
            out["emote"] = scene["defaultEmote"]
        if scene.get("enabled") is False:
            out["enabled"] = False
        if scene.get("macroName"):
            out["macro_name"] = scene["macroName"]
        out["lines"] = lines
        scenes.append(out)
    triggers = []
    for trigger in _list(data.get("triggers")):
        out = {"event": trigger.get("event"), "scene": trigger.get("sceneId"), "chance": trigger.get("chance", 30), "cooldown": trigger.get("cooldown", 60)}
        options = trigger.get("options") or {}
        if trigger.get("event") == "LOW_HEALTH":
            out["threshold"] = options.get("threshold", 30)
        if trigger.get("event") == "SPELL_CAST":
            out["spells"] = [s if s.get("item") else s.get("spell") for s in _list(options.get("spells"))]
        if trigger.get("enabled") is False:
            out["enabled"] = False
        triggers.append(out)
    result: dict[str, Any] = {}
    if character:
        result["character"] = character
    result["target"] = target
    result["scenes"] = scenes
    result["triggers"] = triggers
    pages = _list(data.get("wheelPages"))
    if pages:
        result["wheel"] = [_list(page) for page in pages]
    return result


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value[k] for k in sorted(k for k in value if isinstance(k, int))]
    return []
