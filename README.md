# speakeasy-scribe

[![CI](https://github.com/Hawuawu/speakeasy-scribe/actions/workflows/ci.yml/badge.svg)](https://github.com/Hawuawu/speakeasy-scribe/actions/workflows/ci.yml)
[![Security](https://github.com/Hawuawu/speakeasy-scribe/actions/workflows/security.yml/badge.svg)](https://github.com/Hawuawu/speakeasy-scribe/actions/workflows/security.yml)
[![CodeQL](https://github.com/Hawuawu/speakeasy-scribe/actions/workflows/codeql.yml/badge.svg)](https://github.com/Hawuawu/speakeasy-scribe/actions/workflows/codeql.yml)
![coverage](https://raw.githubusercontent.com/Hawuawu/speakeasy-scribe/badges/coverage.svg)
![tests](https://raw.githubusercontent.com/Hawuawu/speakeasy-scribe/badges/tests.svg)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Write character-specific roleplay scenes for the WoW addon
[SpeakEasy: Emote Wheel, Quick Chat & Roleplay Lines](https://www.curseforge.com/wow/addons/speakeasy-emote-wheel-quick-chat-roleplay-lines)
as YAML, preview them as chat in a browser, and merge them into SpeakEasy's saved data. Made for
WoW Forever; works with any client SpeakEasy supports. SpeakEasy has no import window yet, so this tool
writes its `SpeakEasy.lua` SavedVariables file directly.

- One profile per character: race, class, personality and speech habits guide an AI agent
  ([AGENTS.md](AGENTS.md)) so your elf and your human sound different.
- `preview` renders an HTML page: every line as it appears in chat, the emote wheel, triggers and problems.
- `apply` validates against SpeakEasy's rules, keeps your in-game scenes and settings, and backs up the file.

## Authoring machine (AI agent)

```bash
git clone https://github.com/Hawuawu/speakeasy-scribe && cd speakeasy-scribe
pip install -e ".[dev]"
speakeasy-scribe new "Aelindra" --realm "Argent Dawn" --race "Night Elf" --class Druid
# ask your agent to write scenes in characters/aelindra/ following AGENTS.md
speakeasy-scribe validate characters/aelindra
speakeasy-scribe preview characters/aelindra -o aelindra.html   # open in a browser
```

## Game PC (minimal)

Either download `speakeasy-scribe.exe` from [Releases](https://github.com/Hawuawu/speakeasy-scribe/releases)
(no Python needed) or `pip install git+https://github.com/Hawuawu/speakeasy-scribe` (Python ≥ 3.10 and PyYAML).
Copy the `characters/` folder over, **close WoW completely**, then:

```bash
speakeasy-scribe list --game-dir "C:\Program Files (x86)\World of Warcraft\_forever_"   # accounts and characters
speakeasy-scribe apply characters/aelindra --game-dir "<same folder>" --dry-run        # show changes
speakeasy-scribe apply characters/aelindra --game-dir "<same folder>"
```

`--game-dir` is the client folder that contains `WTF`. Set it once with the `SPEAKEASY_GAME_DIR`
environment variable or a `.scribe.yaml` file (`game_dir: ...`, `account: ...`) in the current folder.
The character must have logged in once with SpeakEasy enabled so its folder exists. Start WoW and open
`/speakeasy`.

To pull existing scenes into YAML: `speakeasy-scribe export --game-dir ... --realm "Argent Dawn" --character Aelindra -o existing.yaml`.

## Commands

| Command | What it does |
|---|---|
| `validate <profile>` | Check against SpeakEasy's rules (`--json` for machines) |
| `preview <profile> [-o file.html]` | Write the HTML preview |
| `apply <profile> [--dry-run] [--replace] [--out file]` | Merge into `SpeakEasy.lua` with a backup |
| `export [--realm R --character C \| --account-wide \| --file F]` | Stored scenes back to YAML |
| `list` | Accounts and characters found in `WTF` |
| `new <name> --realm R` | Scaffold a profile |
| `reference` | Channels, trigger events, variables and limits |

Profile format: [docs/format.md](docs/format.md). Voice notes per race and class: [docs/voices.md](docs/voices.md).

## Limits

SpeakEasy's triggers are combat start/end, low health, death, spell cast, eat/drink, mount, rest area and
targeting an NPC. There is no "joined a party" trigger; put such a scene on the wheel or a button.

## Security

- **CI:** ruff lint (including docstrings, annotations and complexity ≤ 10) and format, `mypy --strict`, pytest with ≥ 90 % coverage on Linux and Windows, Python 3.10 and 3.13, and a
  check that SpeakEasy's own load-time clean-up keeps every scene we write.
- **Security workflow:** Semgrep SAST (`p/python`, `p/secrets`, `p/github-actions`), Ruff bandit rules,
  gitleaks over full history, pip-audit, and an OWASP ZAP baseline DAST scan of generated previews served
  with hardened headers ([`.zap/rules.tsv`](.zap/rules.tsv) lists accepted findings).
- **CodeQL** (`security-extended`) for Python and GitHub Actions; Dependabot for pip and Actions.
- SavedVariables are parsed as data; Lua code in them is rejected, never executed. Previews contain no
  scripts and carry a strict Content Security Policy.

## License

[MIT](LICENSE). Tests include SpeakEasy's MIT-licensed `SpeakEasy_Db.lua` (see `tests/upstream/`).
