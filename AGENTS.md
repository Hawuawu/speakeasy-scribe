# AGENTS.md — writing SpeakEasy scenes with speakeasy-scribe

You are writing **roleplay lines for one World of Warcraft character** (WoW Forever, interface 16001).
The lines live in YAML profiles under `characters/<name>/`. `speakeasy-scribe` checks them, renders a
preview and merges them into the [SpeakEasy](https://www.curseforge.com/wow/addons/speakeasy-emote-wheel-quick-chat-roleplay-lines)
addon's SavedVariables file. SpeakEasy then plays a random line from a scene when the player presses a
button, uses the emote wheel, or a trigger fires.

## Workflow

```bash
pip install -e ".[dev]"                                     # once
speakeasy-scribe new "Aelindra" --realm "Argent Dawn" --race "Night Elf" --class Druid   # new character
speakeasy-scribe reference                                  # channels, events, variables, limits
# edit characters/aelindra/*.yaml
speakeasy-scribe validate characters/aelindra               # must report 0 errors
speakeasy-scribe preview characters/aelindra -o aelindra.html   # show this to the user
```

- **Always** run `validate` after editing, and fix every error. Fix warnings unless the user wants them.
- **Always** run `preview` and point the user at the HTML file before they apply. It shows each line as it
  appears in chat with sample values filled in, the wheel, the triggers and any problems.
- You do **not** run `apply` on the authoring machine. The user copies the `characters/` folder to the game
  PC and runs `speakeasy-scribe apply characters/<name>` there with WoW closed. Never edit `SpeakEasy.lua` by hand.
- To start from what the player already has in game: `speakeasy-scribe export --game-dir <WoW> --realm R --character C -o characters/c/existing.yaml`.
- Only use what `speakeasy-scribe reference` lists. Do not invent channels, events, variables or settings.

## Profile layout

One folder per character. Every `*.yaml` file in it is merged, so split by theme (`character.yaml`,
`social.yaml`, `combat.yaml`, ...). Full schema: [`docs/format.md`](docs/format.md). Examples:
[`examples/characters/aelindra`](examples/characters/aelindra) (Night Elf druid) and
[`examples/characters/tomas`](examples/characters/tomas) (Human warrior).

```yaml
character:            # who is speaking; voice fields are notes for you, SpeakEasy never sees them
  name: Aelindra      # exactly as in game; with realm, finds WTF/Account/<ACC>/<Realm>/<Name>
  realm: Argent Dawn
  race: Night Elf
  class: Druid
  personality: [patient, wry]
  voice: { register: formal, habits: [...], avoid: [...] }
  background: ...
target: character     # character = this character's own scenes; account = shared by all characters
use_own: true

scenes:
  - name: Greeting    # max 32 bytes; id is derived (lower case, letters/digits) unless given
    channel: SAY      # SAY EMOTE YELL PARTY RAID INSTANCE_CHAT AUTO
    emote: BOW        # optional default emote for every line
    lines:
      - "Ishnu-alah, {targetName}."
      - { text: "Elune watches over you.", emote: WAVE }
      - { emote: BOW }               # emote only, no text
triggers:
  - { event: ENTER_COMBAT, scene: battle, chance: 25, cooldown: 90 }
wheel:                 # optional; up to 9 pages of 8 slots: scene ids, "emote:TOKEN" or ""
  - [greeting, battle, "emote:DANCE"]
```

## Writing for the character

Read `character:` first and keep every line in that voice. [`docs/voices.md`](docs/voices.md) has
starting points per race and class; the profile's own `voice` notes always win.

- **Race shapes vocabulary, not stereotypes.** Night Elves: formal, ancient, Elune, Darnassian greetings
  ("Ishnu-alah"). Humans: plain, the Light, Stormwind. Dwarves: hearty, Khaz Modan, ale and stone.
  Orcs: blunt, honour, "Lok'tar". Blood Elves: refined, proud, "Bal'a dash". Mix with personality: a shy
  dwarf is still a dwarf, but shy.
- **Class and job shape topics**: a druid speaks of balance and the wild, a warrior of steel and drills,
  a priest of faith, a rogue avoids straight answers.
- **Write several variations per scene** (at least 3, ideally 5–8). SpeakEasy shuffles them and never
  repeats until every line has been used, so variety is what makes the character feel alive.
- **Stay in character and in setting.** No modern slang, real-world references, or meta talk ("lol").
  Respect `voice.avoid`.
- **Keep it short.** Chat lines are read in passing; aim for under 120 characters. Hard limit 255 bytes
  (accented letters count double).
- **EMOTE channel lines are third person without the name**: `"draws her blade."` shows as
  "Aelindra draws her blade." Speech inside an emote goes in double quotes; Total RP 3 colours it.
- **SAY/YELL lines are spoken words only**, no asterisks. Use an emote line or `emote:` for actions.
- **Use variables** for context: `{targetName}`, `{zone}`, `{timeOfDay}`, `{playerRace}`... (full list via
  `reference`). `{targetName}` falls back to "friend" when nothing is targeted, so lines must read well
  either way. `{spellName}` and `{itemName}` only fill in from `SPELL_CAST` / `EAT_DRINK` triggers.
- Gender: use the pronouns in `character.gender`; ask if it is empty and you need them.

## Triggers

SpeakEasy supports exactly these events: `ENTER_COMBAT`, `LEAVE_COMBAT`, `LOW_HEALTH` (with `threshold`),
`DEATH`, `SPELL_CAST` (with `spells`), `EAT_DRINK`, `MOUNT`, `REST_AREA`, `TARGET_NPC`.

- Keep `chance` low (10–40) and `cooldown` long (60+ seconds) for frequent events, or the character
  becomes spam. SpeakEasy also waits `globalTriggerGap` seconds between any two triggered lines.
- There is **no party, group-join, whisper, quest or level-up trigger**. If the user asks for one ("say
  hello when added to a party"), do not invent an event: explain this, and offer a normal scene they put on
  the wheel or an action-bar button instead (or `/speakeasy <sceneid>` in a macro). Adding new events would
  need a change to SpeakEasy itself.
- Outdoors, triggered SAY/YELL lines wait for the player's next key press (a Blizzard restriction);
  EMOTE/PARTY/RAID lines go out at once.

## YAML gotchas

- Quote every line: `"..."`. A line starting with `{` (like `{targetName} looks tired`) **must** be quoted
  or YAML reads it as a mapping. `yes`, `no`, `on`, `off` unquoted become true/false.
- Never use `|` inside a line (it starts a WoW escape code) or line breaks.
- Emote tokens are upper case: `BOW`, `WAVE`, `CHEER`, `DANCE`, `SALUTE`, `LAUGH`, `THANK`, `KNEEL`...
- Scene ids must be unique per character and not `mute`, `speak` or `debug`.

## Changing this tool

Python ≥ 3.9, PyYAML only at runtime. Code in `src/speakeasy_scribe/`:
`luadata.py` (data-only Lua SavedVariables reader/writer; never executes Lua), `speakeasy.py` (SpeakEasy's
rules), `model.py` (YAML → validated scenes), `savedvars.py` (WTF paths, merge, backups), `preview.py`
(HTML), `cli.py`. Run `ruff check . && ruff format --check . && pytest` before committing (pre-commit runs
ruff; pre-push runs pytest). `tests/test_upstream.py` runs SpeakEasy's real `L.Db.Load` (needs `lua5.1`)
over our output; keep it passing when SpeakEasy's format changes.
