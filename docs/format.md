# Profile format

A profile is one folder (or file list) of YAML files. All files are merged: `scenes` and `triggers`
lists are concatenated, `character`, `settings` and `preview` mappings are combined, and `wheel` may be
set in only one file. Run `speakeasy-scribe reference` for the live list of allowed values.

## Top level

| Key | Type | Meaning |
|---|---|---|
| `character` | mapping | Who speaks. `name` and `realm` locate the character's folder in `WTF` (case-insensitive); `account` is needed only with several WTF accounts. Any other keys (`race`, `class`, `faction`, `gender`, `age`, `personality`, `voice`, `background`, `guild`) are notes for the writer and fill `{playerRace}` etc. in the preview. |
| `target` | `character` \| `account` | `character` writes `SpeakEasyCharDB` in `WTF/Account/<ACC>/<Realm>/<Name>/SavedVariables/SpeakEasy.lua`. `account` writes `SpeakEasyDB` in `WTF/Account/<ACC>/SavedVariables/SpeakEasy.lua`, shared by every character without its own scenes. Default `character`. |
| `use_own` | bool | For `target: character`: switch the character to its own scenes (SpeakEasy's "This character has its own scenes"). Default `true`. |
| `settings` | mapping | SpeakEasy settings (always account-wide): `triggersMuted`, `speakOnAnyKey`, `wheelScale` (0.5–2), `wheelRememberPage`, `primeTimeout` (3–60 s), `globalTriggerGap` (0–300 s), `targetFallback`, `minimapAngle`. |
| `scenes` | list | See below. |
| `triggers` | list | See below. |
| `wheel` | list of pages | 1–9 pages, each up to 8 slots: a scene id or name, `"emote:TOKEN"`, or `""`. Omit to keep the wheel already stored. |
| `preview` | mapping | `samples:` values used for variables in the HTML preview, e.g. `{targetName: Varian, zone: Ashenvale}`. |

## Scenes

| Key | Default | Rule |
|---|---|---|
| `name` | required | ≤ 32 bytes |
| `id` | from name | lower-case letters and digits, unique, not `mute`/`speak`/`debug`; used by `/speakeasy <id>`, triggers and the wheel |
| `channel` | `SAY` | `SAY`, `EMOTE`, `YELL`, `PARTY`, `RAID`, `INSTANCE_CHAT`, `AUTO` (party/raid/instance chat by group, else say) |
| `emote` | none | default emote token played with each line that has none |
| `icon` | 134400 | texture file ID shown on the wheel and the action-bar button |
| `cooldown` | 2 | seconds between lines of this scene, 0–3600 |
| `enabled` | true | |
| `macro_name` | none | ≤ 16 bytes; name of the macro SpeakEasy creates for the scene |
| `lines` | `[]` | each a quoted string, or `{text, emote, enabled}`; text ≤ 255 bytes, no `|`, no line breaks; a line needs text or an emote |
| `notes` | none | free text for the writer, not written to the game |

## Triggers

| Key | Default | Rule |
|---|---|---|
| `event` | required | `ENTER_COMBAT`, `LEAVE_COMBAT`, `LOW_HEALTH`, `DEATH`, `SPELL_CAST`, `EAT_DRINK`, `MOUNT`, `REST_AREA`, `TARGET_NPC` |
| `scene` | required | scene id or name from the profile, or the id of a scene already in the game |
| `chance` | 30 | percent, 0–100 |
| `cooldown` | 60 | seconds, 0–3600 |
| `threshold` | 30 | `LOW_HEALTH` only, percent 1–99 |
| `spells` | — | `SPELL_CAST` only, 1–50 entries: a spell name, or `{spell, item}` for a spell cast by an item |
| `enabled` | true | |

## How `apply` merges

- Scenes are matched by `id`: profile scenes replace stored ones with the same id, new ones are added at
  the end, every other stored scene is kept.
- Stored triggers that point at a profile scene are replaced by the profile's triggers; other triggers
  are kept.
- `wheel`, if given, replaces the stored wheel pages.
- `--replace` drops every stored scene and trigger first. `--dry-run` prints the changes and writes nothing.
- The old file is kept as `SpeakEasy.lua.<date-time>.bak` next to it.
- SpeakEasy cleans its data on load; `tests/test_upstream.py` checks that it keeps everything we write.
