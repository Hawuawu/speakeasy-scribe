"""SpeakEasy's building blocks (lines, scenes, triggers, wheel) as typed objects.

Each class parses its YAML form, reporting problems to a :class:`~.issues.Scope`,
and converts to and from the tables SpeakEasy stores in ``SpeakEasy.lua``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import speakeasy as se
from .issues import Scope
from .luadata import as_list, as_table

SCENE_KEYS = {"id", "name", "channel", "icon", "cooldown", "emote", "enabled", "macro_name", "lines", "notes"}
LINE_KEYS = {"text", "emote", "enabled"}
TRIGGER_KEYS = {"event", "scene", "chance", "cooldown", "enabled", "threshold", "spells"}
ID_PATTERN = re.compile(r"^[a-z0-9]+$")
VARIABLE_PATTERN = re.compile(r"\{(\w+)\}")
_EMOTE = re.compile(r"^[A-Z0-9_]+$")

DEFAULT_SCENE_COOLDOWN = 2
DEFAULT_CHANCE = 30
DEFAULT_TRIGGER_COOLDOWN = 60
DEFAULT_THRESHOLD = 30

SceneResolver = Callable[[Any], "str | None"]


def nbytes(text: str) -> int:
    """Length in bytes, which is how WoW measures chat and name limits."""
    return len(text.encode("utf-8", errors="surrogateescape"))


def derive_id(name: str) -> str:
    """Make a scene id the way SpeakEasy does: lower case, letters and digits only."""
    return re.sub(r"[^0-9a-z]", "", str(name).lower()) or "scene"


def parse_emote(scope: Scope, emote: Any) -> str | None:
    """Return a valid emote token such as ``BOW``, or ``None`` when blank or invalid."""
    if emote is None or emote == "":
        return None
    if not isinstance(emote, str) or not _EMOTE.match(emote) or nbytes(emote) > se.MAX_EMOTE_BYTES:
        scope.error(f"emote {emote!r} must be an upper-case emote token such as BOW or WAVE")
        return None
    return emote


def check_text(scope: Scope, text: str) -> None:
    """Report what would break or be cut when SpeakEasy sends ``text`` to chat."""
    if "\n" in text or "\r" in text:
        scope.error("a line cannot contain a line break; split it into two lines")
    if "|" in text:
        scope.error("'|' starts a WoW escape code and breaks chat; remove it")
    if nbytes(text) > se.MAX_LINE_BYTES:
        scope.error(f"line is {nbytes(text)} bytes; SpeakEasy cuts lines at {se.MAX_LINE_BYTES}")
    for name in VARIABLE_PATTERN.findall(text):
        if name not in se.VARIABLES:
            scope.warn(f"unknown variable {{{name}}} is sent as typed")


@dataclass(frozen=True)
class Line:
    """One thing a scene can say: chat text, an emote, or both."""

    text: str
    emote: str | None = None
    enabled: bool = True

    @classmethod
    def parse(cls, raw: Any, scope: Scope) -> Line | None:
        """Read a line given as a quoted string or as ``text:/emote:/enabled:`` keys."""
        mapping = cls._mapping(raw, scope)
        if mapping is None:
            return None
        text = mapping.get("text") or ""
        if not isinstance(text, str):
            scope.error("text must be a quoted string")
            return None
        check_text(scope, text)
        emote = parse_emote(scope, mapping.get("emote"))
        if not text.strip() and not emote:
            scope.error("line has neither text nor an emote")
            return None
        return cls(text, emote, scope.flag(mapping.get("enabled", True)))

    @staticmethod
    def _mapping(raw: Any, scope: Scope) -> dict[str, Any] | None:
        if isinstance(raw, str):
            return {"text": raw}
        if not isinstance(raw, dict):
            scope.error(f"line must be text in quotes, got {type(raw).__name__} {raw!r}")
            return None
        if not set(raw) <= LINE_KEYS:
            scope.error("a line starting with '{' must be quoted, or use text:/emote:/enabled: keys")
            return None
        return raw

    @classmethod
    def from_speakeasy(cls, data: dict[str, Any]) -> Line:
        """Read a line stored by SpeakEasy."""
        return cls(str(data.get("text") or ""), data.get("emote") or None, data.get("enabled", True) is not False)

    @property
    def variables(self) -> set[str]:
        """Names of the ``{variables}`` used in the text."""
        return set(VARIABLE_PATTERN.findall(self.text))

    def to_speakeasy(self) -> dict[str, Any]:
        """Return the table SpeakEasy stores for this line."""
        data: dict[str, Any] = {"text": self.text}
        if self.emote:
            data["emote"] = self.emote
        data["enabled"] = self.enabled
        return data

    def to_yaml(self) -> str | dict[str, Any]:
        """Return the shortest YAML form: plain text when that is all there is."""
        if not self.emote and self.enabled:
            return self.text
        data: dict[str, Any] = {"text": self.text} if self.text else {}
        if self.emote:
            data["emote"] = self.emote
        if not self.enabled:
            data["enabled"] = False
        return data


@dataclass(frozen=True)
class Scene:
    """A pool of lines SpeakEasy picks from for one situation."""

    id: str
    name: str
    lines: tuple[Line, ...] = ()
    channel: str = "SAY"
    icon: int = se.DEFAULT_ICON
    cooldown: float = DEFAULT_SCENE_COOLDOWN
    default_emote: str | None = None
    enabled: bool = True
    macro_name: str | None = None
    where: str = field(default="", compare=False)

    @classmethod
    def parse(cls, raw: Any, scope: Scope, taken: set[str]) -> Scene | None:
        """Read a scene; ``taken`` holds the ids already used and gets this one added."""
        if not isinstance(raw, dict):
            scope.error("scene must be a mapping")
            return None
        scope.unknown_keys(raw, SCENE_KEYS, "scene key")
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            scope.error("scene needs a name")
            return None
        scope = scope.child(f" '{name}'")
        if nbytes(name) > se.MAX_NAME_BYTES:
            scope.error(f"name is longer than {se.MAX_NAME_BYTES} bytes")
        return cls(
            id=_scene_id(scope, raw.get("id", derive_id(name)), taken),
            channel=_channel(scope, raw.get("channel", "SAY")),
            icon=_icon(scope, raw.get("icon", se.DEFAULT_ICON)),
            cooldown=scope.number(raw.get("cooldown"), "cooldown", se.COOLDOWN_RANGE, DEFAULT_SCENE_COOLDOWN),
            macro_name=_macro_name(scope, raw.get("macro_name")),
            lines=_lines(scope, raw.get("lines")),
            default_emote=parse_emote(scope, raw.get("emote")),
            enabled=scope.flag(raw.get("enabled", True)),
            name=name.strip(),
            where=scope.where,
        )

    @classmethod
    def from_speakeasy(cls, data: dict[str, Any]) -> Scene:
        """Read a scene stored by SpeakEasy."""
        return cls(
            id=str(data.get("id") or ""),
            name=str(data.get("name") or ""),
            lines=tuple(Line.from_speakeasy(line) for line in as_list(data.get("lines")) if isinstance(line, dict)),
            channel=str(data.get("channel") or "SAY"),
            icon=data.get("icon", se.DEFAULT_ICON),
            cooldown=data.get("cooldown", DEFAULT_SCENE_COOLDOWN),
            default_emote=data.get("defaultEmote") or None,
            enabled=data.get("enabled") is not False,
            macro_name=data.get("macroName") or None,
        )

    @property
    def has_enabled_lines(self) -> bool:
        """Whether SpeakEasy has anything to say for this scene."""
        return any(line.enabled for line in self.lines)

    def to_speakeasy(self) -> dict[str, Any]:
        """Return the table SpeakEasy stores for this scene."""
        data: dict[str, Any] = {"id": self.id, "name": self.name, "icon": self.icon, "channel": self.channel}
        if self.default_emote:
            data["defaultEmote"] = self.default_emote
        data.update(cooldown=self.cooldown, enabled=self.enabled)
        if self.macro_name:
            data["macroName"] = self.macro_name
        data["lines"] = [line.to_speakeasy() for line in self.lines]
        return data

    def to_yaml(self) -> dict[str, Any]:
        """Return the profile YAML for this scene, leaving out defaults."""
        data: dict[str, Any] = {"id": self.id, "name": self.name, "channel": self.channel}
        optional = {
            "icon": (self.icon, se.DEFAULT_ICON),
            "cooldown": (self.cooldown, DEFAULT_SCENE_COOLDOWN),
            "emote": (self.default_emote, None),
            "enabled": (self.enabled, True),
            "macro_name": (self.macro_name, None),
        }
        data.update({key: value for key, (value, default) in optional.items() if value != default})
        data["lines"] = [line.to_yaml() for line in self.lines]
        return data


def _scene_id(scope: Scope, scene_id: Any, taken: set[str]) -> str:
    if not isinstance(scene_id, str) or not ID_PATTERN.match(scene_id):
        scope.error("id must be lower-case letters and digits only")
    elif scene_id in se.RESERVED_IDS:
        scope.error(f"id '{scene_id}' is reserved by /speakeasy")
    elif scene_id in taken:
        scope.error(f"id '{scene_id}' is used by another scene; set a different id")
    taken.add(str(scene_id))
    return str(scene_id)


def _channel(scope: Scope, channel: Any) -> str:
    if channel not in se.CHANNELS:
        scope.error(f"channel must be one of {', '.join(se.CHANNELS)}")
    return str(channel)


def _icon(scope: Scope, icon: Any) -> int:
    if isinstance(icon, bool) or not isinstance(icon, int):
        scope.error("icon must be a texture file ID (a whole number)")
        return se.DEFAULT_ICON
    return icon


def _macro_name(scope: Scope, macro: Any) -> str | None:
    if macro is None:
        return None
    if not isinstance(macro, str) or nbytes(macro) > se.MAX_MACRO_NAME_BYTES:
        scope.error(f"macro_name must be text of at most {se.MAX_MACRO_NAME_BYTES} bytes")
        return None
    return macro


def _lines(scope: Scope, raw: Any) -> tuple[Line, ...]:
    if raw is not None and not isinstance(raw, list):
        scope.error("lines must be a list")
        raw = None
    parsed = (Line.parse(item, scope.child(f" line {index}")) for index, item in enumerate(raw or [], start=1))
    lines = tuple(line for line in parsed if line)
    if not any(line.enabled for line in lines):
        scope.warn("scene has no enabled lines")
    return lines


@dataclass(frozen=True)
class Spell:
    """A spell that sets off a ``SPELL_CAST`` trigger; ``item`` fills ``{itemName}``."""

    spell: str
    item: str | None = None

    @classmethod
    def parse(cls, raw: Any, scope: Scope) -> Spell | None:
        """Read a spell given as a name or as ``spell:/item:`` keys."""
        if isinstance(raw, str):
            raw = {"spell": raw}
        if not isinstance(raw, dict) or not isinstance(raw.get("spell"), str) or not raw["spell"].strip():
            scope.error("each spell must be a name, or spell:/item: keys")
            return None
        if any(nbytes(str(value)) > se.MAX_SPELL_BYTES for value in raw.values()):
            scope.error(f"spell and item names are limited to {se.MAX_SPELL_BYTES} bytes")
        return cls(raw["spell"], str(raw["item"]) if raw.get("item") else None)

    @classmethod
    def from_speakeasy(cls, data: dict[str, Any]) -> Spell:
        """Read a spell stored by SpeakEasy."""
        return cls(str(data.get("spell") or ""), str(data["item"]) if data.get("item") else None)

    def to_speakeasy(self) -> dict[str, str]:
        """Return the table SpeakEasy stores for this spell."""
        return {"spell": self.spell, "item": self.item} if self.item else {"spell": self.spell}

    def to_yaml(self) -> str | dict[str, str]:
        """Return the spell name, or both keys when an item is set."""
        return self.to_speakeasy() if self.item else self.spell


@dataclass(frozen=True)
class Trigger:
    """Plays a scene when something happens in game."""

    event: str
    scene_id: str
    chance: float = DEFAULT_CHANCE
    cooldown: float = DEFAULT_TRIGGER_COOLDOWN
    enabled: bool = True
    threshold: float = DEFAULT_THRESHOLD
    spells: tuple[Spell, ...] | None = None
    where: str = field(default="", compare=False)

    @classmethod
    def parse(cls, raw: Any, scope: Scope, resolve: SceneResolver) -> Trigger | None:
        """Read a trigger; ``resolve`` maps a scene id or name to the scene's id."""
        if not isinstance(raw, dict):
            scope.error("trigger must be a mapping")
            return None
        scope.unknown_keys(raw, TRIGGER_KEYS, "trigger key")
        event = raw.get("event")
        if event not in se.EVENTS:
            scope.error(f"event must be one of {', '.join(se.EVENTS)}; SpeakEasy has no other triggers")
            return None
        scene_id = _trigger_scene(scope, raw.get("scene"), resolve)
        if scene_id is None:
            return None
        if "threshold" in raw and event != "LOW_HEALTH":
            scope.warn("threshold only matters for LOW_HEALTH")
        return cls(
            event=event,
            scene_id=scene_id,
            # SpeakEasy stores a threshold on every trigger; writing it keeps files identical after its clean-up.
            threshold=scope.number(raw.get("threshold"), "threshold", se.THRESHOLD_RANGE, DEFAULT_THRESHOLD),
            spells=_spells(scope, event, raw),
            chance=scope.number(raw.get("chance"), "chance", se.CHANCE_RANGE, DEFAULT_CHANCE),
            cooldown=scope.number(raw.get("cooldown"), "cooldown", se.COOLDOWN_RANGE, DEFAULT_TRIGGER_COOLDOWN),
            enabled=scope.flag(raw.get("enabled", True)),
            where=scope.where,
        )

    @classmethod
    def from_speakeasy(cls, data: dict[str, Any]) -> Trigger:
        """Read a trigger stored by SpeakEasy."""
        options = as_table(data.get("options"))
        event = str(data.get("event") or "")
        spells = as_list(options.get("spells"))
        return cls(
            event=event,
            scene_id=str(data.get("sceneId") or ""),
            chance=data.get("chance", DEFAULT_CHANCE),
            cooldown=data.get("cooldown", DEFAULT_TRIGGER_COOLDOWN),
            enabled=data.get("enabled") is not False,
            threshold=options.get("threshold", DEFAULT_THRESHOLD),
            spells=tuple(Spell.from_speakeasy(s) for s in spells if isinstance(s, dict)) if event == "SPELL_CAST" else None,
        )

    def to_speakeasy(self) -> dict[str, Any]:
        """Return the table SpeakEasy stores for this trigger."""
        options: dict[str, Any] = {"threshold": self.threshold}
        if self.spells is not None:
            options["spells"] = [spell.to_speakeasy() for spell in self.spells]
        return {
            "event": self.event,
            "sceneId": self.scene_id,
            "chance": self.chance,
            "cooldown": self.cooldown,
            "enabled": self.enabled,
            "options": options,
        }

    def to_yaml(self) -> dict[str, Any]:
        """Return the profile YAML for this trigger."""
        data: dict[str, Any] = {"event": self.event, "scene": self.scene_id, "chance": self.chance, "cooldown": self.cooldown}
        if self.event == "LOW_HEALTH":
            data["threshold"] = self.threshold
        if self.spells is not None:
            data["spells"] = [spell.to_yaml() for spell in self.spells]
        if not self.enabled:
            data["enabled"] = False
        return data


def _trigger_scene(scope: Scope, ref: Any, resolve: SceneResolver) -> str | None:
    scene_id = resolve(ref)
    if scene_id is not None:
        return scene_id
    if isinstance(ref, str) and ID_PATTERN.match(ref):
        scope.warn(f"scene '{ref}' is not in this profile; it must already exist in SpeakEasy")
        return ref
    scope.error(f"scene {ref!r} not found")
    return None


def _spells(scope: Scope, event: str, raw: dict[str, Any]) -> tuple[Spell, ...] | None:
    if event != "SPELL_CAST":
        if "spells" in raw:
            scope.error("spells only apply to SPELL_CAST")
        return None
    items = raw.get("spells") or []
    parsed = (Spell.parse(item, scope) for item in (items if isinstance(items, list) else [items]))
    spells = tuple(spell for spell in parsed if spell)
    if not spells:
        scope.error("SPELL_CAST needs a list of spells")
    if len(spells) > se.MAX_TRIGGER_SPELLS:
        scope.error(f"at most {se.MAX_TRIGGER_SPELLS} spells per trigger")
    return spells


@dataclass(frozen=True)
class Wheel:
    """The emote wheel: pages of eight slots holding a scene id, ``emote:TOKEN`` or nothing."""

    pages: tuple[tuple[str, ...], ...]

    @classmethod
    def parse(cls, raw: Any, scope: Scope, resolve: SceneResolver) -> Wheel | None:
        """Read the wheel; slots may name scenes by id or name."""
        if not isinstance(raw, list) or not all(isinstance(page, list) for page in raw):
            scope.error("wheel must be a list of pages, each a list of up to 8 slots")
            return None
        if not 1 <= len(raw) <= se.MAX_WHEEL_PAGES:
            scope.error(f"wheel needs 1 to {se.MAX_WHEEL_PAGES} pages")
        return cls(tuple(_page(scope.report.at(f"wheel page {number}"), page, resolve) for number, page in enumerate(raw, start=1)))

    @classmethod
    def first_scenes(cls, scenes: list[Scene]) -> Wheel:
        """Build the page SpeakEasy makes when it has no wheel: the first eight scenes."""
        return cls((tuple(scene.id for scene in scenes[: se.WHEEL_SLOTS]),))

    def to_speakeasy(self) -> list[list[str]]:
        """Return SpeakEasy's ``wheelPages`` table."""
        return [list(page) for page in self.pages]


def _page(scope: Scope, page: list[Any], resolve: SceneResolver) -> tuple[str, ...]:
    if len(page) > se.WHEEL_SLOTS:
        scope.error(f"a page has {se.WHEEL_SLOTS} slots")
    slots = [_slot(scope, slot, resolve) for slot in page[: se.WHEEL_SLOTS]]
    return tuple(slots + [""] * (se.WHEEL_SLOTS - len(slots)))


def _slot(scope: Scope, slot: Any, resolve: SceneResolver) -> str:
    if slot in (None, ""):
        return ""
    if isinstance(slot, str) and slot.startswith(se.EMOTE_SLOT_PREFIX):
        parse_emote(scope, slot[len(se.EMOTE_SLOT_PREFIX) :])
        return slot
    scene_id = resolve(slot)
    if scene_id:
        return scene_id
    scope.error(f"slot {slot!r} is not a scene in this profile or emote:TOKEN")
    return ""
