"""A self-contained HTML page showing a profile's scenes as they would look in WoW chat."""

from __future__ import annotations

import html
import math
import re
from typing import Any

from . import speakeasy as se
from .model import Profile, nbytes

CHAT = {
    "SAY": ("#ffffff", "{name} says: {text}"),
    "YELL": ("#ff4040", "{name} yells: {text}"),
    "EMOTE": ("#ff8040", "{name} {text}"),
    "PARTY": ("#aaaaff", "[Party] [{name}]: {text}"),
    "RAID": ("#ff7f00", "[Raid] [{name}]: {text}"),
    "INSTANCE_CHAT": ("#ff7f00", "[Instance] [{name}]: {text}"),
    "AUTO": ("#aaaaff", "[Party] [{name}]: {text}"),
}
DEFAULT_SAMPLES = {
    "targetName": "Varian",
    "targetClass": "Warrior",
    "targetRace": "Human",
    "zone": "Elwynn Forest",
    "subZone": "Lion's Pride Inn",
    "guild": "",
    "timeOfDay": "evening",
    "healthPercent": "35%",
    "spellName": "Fireball",
    "itemName": "Conjured Bread",
}
_VARIABLE = re.compile(r"\{(\w+)\}")
_QUOTED = re.compile(r"(&quot;.*?&quot;|“.*?”)")

CSS = """
:root{color-scheme:dark}*{box-sizing:border-box}
body{margin:0;font:14px/1.45 system-ui,Segoe UI,Arial,sans-serif;background:#14110d;color:#e8dcc0}
header{padding:20px 28px;background:linear-gradient(#2a2116,#1a150f);border-bottom:2px solid #6b5326}
h1{margin:0;font:600 24px Georgia,serif;color:#ffd100}h2{font:600 18px Georgia,serif;color:#ffd100;margin:0 0 8px}
main{padding:20px 28px;display:grid;gap:18px;max-width:1200px}
.meta{color:#bfae8a}.tags span{display:inline-block;margin:4px 6px 0 0;padding:2px 8px;border:1px solid #6b5326;border-radius:10px;font-size:12px}
.card{background:#1e1912;border:1px solid #4a3a1c;border-radius:6px;padding:14px 16px}
.issues li{margin:2px 0}.error{color:#ff6b6b}.warning{color:#ffcc66}.ok{color:#7ed957}
.chat{background:rgba(0,0,0,.55);border-radius:4px;padding:8px 10px;font:13px/1.5 Arial,sans-serif;margin-top:8px}
.chat div{margin:1px 0}.chat .off{opacity:.4;text-decoration:line-through}
.chat .anim{color:#bfae8a;font-style:italic}.chat .bytes{float:right;color:#777;font-size:11px}
.chat .over{color:#ff6b6b}.var{color:#ff4040}.speech{color:#ffffff}
.badge{display:inline-block;padding:1px 7px;border-radius:3px;font-size:12px;margin-right:6px;background:#3a2e17;color:#ffd100}
details{margin-top:8px}summary{cursor:pointer;color:#bfae8a}
pre{white-space:pre-wrap;background:#0d0b08;padding:8px;border-radius:4px;font-size:12px}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #3a2e17;padding:5px 8px;text-align:left}
.wheels{display:flex;flex-wrap:wrap;gap:18px}
.wheel{position:relative;width:240px;height:240px;border-radius:50%;background:radial-gradient(#2a2116 30%,#1a150f 70%);border:2px solid #6b5326}
.wheel .hub{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);color:#bfae8a;font-size:12px}
.slot{position:absolute;width:74px;margin:-14px 0 0 -37px;text-align:center;font-size:12px;padding:3px;border-radius:4px;background:#3a2e17;color:#ffd100}
.slot.empty{background:none;color:#555}.slot.emote{color:#e8dcc0}
"""


def _sample_values(profile: Profile) -> dict[str, str]:
    character = profile.character
    values = dict(DEFAULT_SAMPLES)
    values.update(
        playerName=str(character.get("name") or "You"),
        playerClass=str(character.get("class") or ""),
        playerRace=str(character.get("race") or ""),
        guild=str(character.get("guild") or ""),
    )
    values.update({k: str(v) for k, v in (profile.preview.get("samples") or {}).items()})
    return values


def _fill(text: str, values: dict[str, str]) -> tuple[str, str]:
    """(plain filled text, HTML with unknown variables marked red)."""

    def plain(match: re.Match[str]) -> str:
        key = match.group(1)
        return values.get(key, "") if key in se.VARIABLES else match.group(0)

    parts, last = [], 0
    for match in _VARIABLE.finditer(text):
        parts.append(html.escape(text[last : match.start()]))
        key = match.group(1)
        if key in se.VARIABLES:
            parts.append(html.escape(values.get(key, "")))
        else:
            parts.append(f'<span class="var">{html.escape(match.group(0))}</span>')
        last = match.end()
    parts.append(html.escape(text[last:]))
    return _VARIABLE.sub(plain, text).strip(), "".join(parts).strip()


def _chat_line(scene: dict[str, Any], line: dict[str, Any], values: dict[str, str]) -> str:
    color, template = CHAT[scene["channel"]]
    emote = line.get("emote") or scene.get("defaultEmote")
    plain, rich = _fill(line["text"], values)
    out = []
    if emote:
        out.append(f'<span class="anim">/{html.escape(emote.lower())} &mdash; {html.escape(values["playerName"])} performs {html.escape(emote)}</span>')
    if plain:
        name = html.escape(values["playerName"])
        if scene["channel"] == "EMOTE":
            rich = _QUOTED.sub(r'<span class="speech">\1</span>', rich)
        size = nbytes(plain)
        over = " over" if size > se.MAX_LINE_BYTES else ""
        out.append(f'<span style="color:{color}">{template.format(name=name, text=rich)}</span><span class="bytes{over}">{size}/{se.MAX_LINE_BYTES}</span>')
    cls = "" if line.get("enabled", True) else ' class="off"'
    return f"<div{cls}>{'<br>'.join(out)}</div>"


def _scene_card(scene: dict[str, Any], values: dict[str, str], triggers: list[dict[str, Any]]) -> str:
    badges = [scene["channel"], f"cooldown {scene['cooldown']}s", f"/speakeasy {scene['id']}"]
    if scene.get("defaultEmote"):
        badges.append(f"emote {scene['defaultEmote']}")
    if not scene.get("enabled", True):
        badges.append("disabled")
    badges += [f"trigger: {t['event']} ({t['chance']}%)" for t in triggers if t["sceneId"] == scene["id"]]
    raw = "\n".join(f"- {line['text']}" + (f"   [{line['emote']}]" if line.get("emote") else "") for line in scene["lines"])
    lines = "".join(_chat_line(scene, line, values) for line in scene["lines"])
    return (
        f'<section class="card"><h2>{html.escape(scene["name"])}</h2>'
        + "".join(f'<span class="badge">{html.escape(str(b))}</span>' for b in badges)
        + f'<div class="chat">{lines or "<em>no lines</em>"}</div>'
        f"<details><summary>Raw lines</summary><pre>{html.escape(raw)}</pre></details></section>"
    )


def _wheels(profile: Profile) -> str:
    pages = profile.wheel
    note = ""
    if pages is None:
        pages = [[s["id"] for s in profile.scenes[: se.WHEEL_SLOTS]]]
        note = '<p class="meta">No wheel in this profile: SpeakEasy keeps the stored wheel, or fills a new one with the first 8 scenes.</p>'
    names = {s["id"]: s["name"] for s in profile.scenes}
    out = []
    for number, page in enumerate(pages, start=1):
        slots = []
        for index in range(se.WHEEL_SLOTS):
            slot = page[index] if index < len(page) else ""
            angle = -math.pi / 2 + index * 2 * math.pi / se.WHEEL_SLOTS
            left, top = 50 + 38 * math.cos(angle), 50 + 38 * math.sin(angle)
            if not slot:
                label, cls = "empty", "slot empty"
            elif slot.startswith(se.EMOTE_SLOT_PREFIX):
                label, cls = "/" + slot[len(se.EMOTE_SLOT_PREFIX) :].lower(), "slot emote"
            else:
                label, cls = names.get(slot, slot), "slot"
            slots.append(f'<div class="{cls}" style="left:{left:.1f}%;top:{top:.1f}%">{html.escape(label)}</div>')
        out.append(f'<div class="wheel"><div class="hub">page {number}</div>{"".join(slots)}</div>')
    return f'<section class="card"><h2>Emote wheel</h2>{note}<div class="wheels">{"".join(out)}</div></section>'


def _triggers(profile: Profile) -> str:
    if not profile.triggers:
        return ""
    names = {s["id"]: s["name"] for s in profile.scenes}
    rows = []
    for t in profile.triggers:
        options = t.get("options") or {}
        detail = ""
        if "threshold" in options:
            detail = f"below {options['threshold']}% health"
        if options.get("spells"):
            detail = ", ".join(s["spell"] + (f" ({s['item']})" if s.get("item") else "") for s in options["spells"])
        rows.append(
            "<tr>"
            + "".join(
                f"<td>{html.escape(str(c))}</td>"
                for c in (
                    t["event"],
                    se.EVENTS[t["event"]],
                    detail,
                    names.get(t["sceneId"], t["sceneId"]),
                    f"{t['chance']}%",
                    f"{t['cooldown']}s",
                    "yes" if t["enabled"] else "no",
                )
            )
            + "</tr>"
        )
    head = "".join(f"<th>{h}</th>" for h in ("Event", "When", "Details", "Scene", "Chance", "Cooldown", "On"))
    return f'<section class="card"><h2>Triggers</h2><table><tr>{head}</tr>{"".join(rows)}</table></section>'


def _issues(profile: Profile) -> str:
    if not profile.issues:
        return '<section class="card ok">Validation passed: no errors or warnings.</section>'
    items = "".join(f'<li class="{i.level}">{html.escape(str(i))}</li>' for i in profile.issues)
    return f'<section class="card"><h2>Validation</h2><ul class="issues">{items}</ul></section>'


def render(profile: Profile) -> str:
    values = _sample_values(profile)
    character = profile.character
    title = character.get("name") or "SpeakEasy scenes"
    facts = [character.get(k) for k in ("race", "class", "faction", "realm")]
    tags = character.get("personality") or []
    if isinstance(tags, str):
        tags = [tags]
    samples = ", ".join(f"{{{k}}} = {v or '(blank)'}" for k, v in values.items())
    body = [
        f"<header><h1>{html.escape(str(title))}</h1>"
        f'<div class="meta">{html.escape(" · ".join(str(f) for f in facts if f))} &mdash; target: {html.escape(profile.target)}</div>'
        f'<div class="tags">{"".join(f"<span>{html.escape(str(t))}</span>" for t in tags)}</div></header><main>',
        _issues(profile),
        f'<p class="meta">Sample values: {html.escape(samples)}</p>',
        _wheels(profile),
        _triggers(profile),
        *(_scene_card(scene, values, profile.triggers) for scene in profile.scenes),
        "</main>",
    ]
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">"
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(str(title))} — SpeakEasy preview</title><style>{CSS}</style></head><body>" + "".join(body) + "</body></html>"
    )
