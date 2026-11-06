"""Command line: speakeasy-scribe validate|preview|apply|export|list|new|reference."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from . import __version__, model, preview, savedvars
from . import speakeasy as se

CONFIG_FILE = ".scribe.yaml"


class UsageError(Exception):
    """Raised for a missing or conflicting command-line option."""


TEMPLATE = """\
# Character profile for speakeasy-scribe. See AGENTS.md and docs/format.md.
character:
  name: {name}            # exactly as in game (used to find WTF/.../<Realm>/<Name>)
  realm: {realm}
  # account: MYACCOUNT    # only needed when WTF/Account holds more than one account
  race: {race}
  class: {klass}
  faction: {faction}
  gender: ""
  age: ""
  personality: []         # e.g. [proud, curious, dry humour]
  voice:
    register: ""          # e.g. formal, rough, playful
    habits: []            # speech habits, favourite words, greetings
    avoid: []             # words or topics this character never uses
  background: ""
target: character         # 'character' (own scenes for this character) or 'account' (shared)
use_own: true             # make this character use its own scenes in SpeakEasy

scenes: []
triggers: []
# wheel:
#   - [greeting, farewell, "emote:BOW"]
"""


def _config() -> dict[str, Any]:
    """Read ``.scribe.yaml`` from the current folder, if any."""
    path = Path(CONFIG_FILE)
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(data, dict):
            return data
    return {}


def _game_dir(args: argparse.Namespace) -> str | None:
    return args.game_dir or os.environ.get("SPEAKEASY_GAME_DIR") or _config().get("game_dir")


def _account(args: argparse.Namespace) -> str | None:
    return getattr(args, "account", None) or _config().get("account")


def _report(profile: model.Profile, quiet: bool = False) -> bool:
    for issue in profile.issues:
        print(issue, file=sys.stderr)
    if not quiet:
        print(
            f"{len(profile.scenes)} scenes, {sum(len(s.lines) for s in profile.scenes)} lines, "
            f"{len(profile.triggers)} triggers: {len(profile.errors)} errors, {len(profile.warnings)} warnings"
        )
    return not profile.errors


def cmd_validate(args: argparse.Namespace) -> int:
    """Check profiles against SpeakEasy's rules."""
    profile = model.load(args.profile)
    if args.json:
        print(json.dumps({"ok": not profile.errors, "issues": [vars(i) for i in profile.issues]}, indent=2))
        return 0 if not profile.errors else 1
    return 0 if _report(profile) else 1


def cmd_preview(args: argparse.Namespace) -> int:
    """Write the HTML preview of a profile."""
    profile = model.load(args.profile)
    _report(profile)
    out = Path(args.out or f"{_slug(profile.character.get('name') or 'scenes')}-preview.html")
    out.write_text(preview.render(profile), encoding="utf-8")
    print(f"wrote {out}")
    return 0 if not profile.errors else 1


def _print_plan(result: savedvars.Plan, profile: model.Profile, dry_run: bool) -> None:
    change = result.change
    print(f"{'would write' if dry_run else 'writing'} {result.file.path} ({result.file.variable})")
    print(f"  scenes added: {', '.join(change.added) or '-'}")
    print(f"  scenes replaced: {', '.join(change.replaced) or '-'}")
    print(f"  scenes kept: {', '.join(change.kept) or '-'}")
    print(f"  triggers: {change.triggers_removed} removed, {change.triggers_added} added; wheel {'replaced' if change.wheel else 'kept'}")
    if result.settings_file:
        print(f"  settings into {result.settings_file.path}: {', '.join(profile.settings)}")


def cmd_apply(args: argparse.Namespace) -> int:
    """Merge profiles into SpeakEasy.lua, keeping a backup."""
    profile = model.load(args.profile)
    if not _report(profile):
        print("not applied: fix the errors first", file=sys.stderr)
        return 1
    game_dir = _game_dir(args)
    wtf = savedvars.wtf_dir(game_dir) if game_dir and not args.out else None
    result = savedvars.plan(profile, wtf, Path(args.out) if args.out else None, _account(args), args.replace)
    _print_plan(result, profile, args.dry_run)
    if args.dry_run:
        return 0
    for backup in savedvars.apply(result):
        print(f"  backup: {backup}")
    print("done. Start WoW (or /reload if it was closed) and open /speakeasy.")
    return 0


def _export_source(args: argparse.Namespace) -> tuple[Path, dict[str, str]]:
    """Find the file to export and its character (empty for shared scenes)."""
    if args.file:
        return Path(args.file), {}
    game_dir = _game_dir(args)
    if not game_dir:
        raise UsageError("set --game-dir (or SPEAKEASY_GAME_DIR) or give --file")
    wtf = savedvars.wtf_dir(game_dir)
    if args.account_wide:
        return savedvars.account_file(wtf, _account(args)), {}
    if not (args.realm and args.character):
        raise UsageError("give --realm and --character, or --account-wide")
    path = savedvars.character_file(wtf, _account(args), args.realm, args.character)
    character_dir = path.parent.parent
    return path, {"name": character_dir.name, "realm": character_dir.parent.name}


def _read_export(path: Path, account_wide: bool, any_variable: bool) -> tuple[str, dict[str, Any]]:
    """Read the stored set; a file given directly may hold either global."""
    order = [savedvars.ACCOUNT_VAR, savedvars.CHARACTER_VAR]
    if not account_wide:
        order.reverse()
    for variable in order if any_variable else order[:1]:
        data = savedvars.read(path, variable)
        if data is not None:
            return variable, data
    raise UsageError(f"no SpeakEasy data in {path}")


def cmd_export(args: argparse.Namespace) -> int:
    """Turn stored SpeakEasy scenes back into profile YAML."""
    path, character = _export_source(args)
    variable, data = _read_export(path, args.account_wide, bool(args.file))
    target = "account" if variable == savedvars.ACCOUNT_VAR else "character"
    text = yaml.safe_dump(model.from_set(data, character, target), sort_keys=False, allow_unicode=True, width=1000)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(text)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List accounts and characters with their SpeakEasy files."""
    game_dir = _game_dir(args)
    if not game_dir:
        raise UsageError("set --game-dir (or SPEAKEASY_GAME_DIR)")
    wtf = savedvars.wtf_dir(game_dir)
    for account in savedvars.accounts(wtf):
        shared = account / "SavedVariables" / savedvars.FILE_NAME
        print(f"{account.name}: shared SpeakEasy file {'found' if shared.exists() else 'missing'}")
    for account_name, realm, name, path in savedvars.characters(wtf):
        data = savedvars.read(path, savedvars.CHARACTER_VAR) if path.exists() else None
        state = "own scenes" if data and data.get("useOwn") else ("file, shared scenes" if path.exists() else "no file")
        print(f"  {account_name} / {realm} / {name}: {state}")
    return 0


def _slug(text: str) -> str:
    return re.sub(r"[^0-9a-z]+", "-", str(text).lower()).strip("-") or "character"


def cmd_new(args: argparse.Namespace) -> int:
    """Scaffold a character profile."""
    folder = Path(args.dir) / _slug(args.name)
    path = folder / "character.yaml"
    if path.exists():
        print(f"{path} already exists", file=sys.stderr)
        return 1
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(TEMPLATE.format(name=args.name, realm=args.realm, race=args.race, klass=args.klass, faction=args.faction), encoding="utf-8")
    print(f"wrote {path}")
    return 0


def cmd_reference(args: argparse.Namespace) -> int:
    """Print channels, events, variables and limits."""
    data = {
        "channels": list(se.CHANNELS),
        "events": se.EVENTS,
        "variables": se.VARIABLES,
        "limits": {
            "line_bytes": se.MAX_LINE_BYTES,
            "name_bytes": se.MAX_NAME_BYTES,
            "wheel_slots": se.WHEEL_SLOTS,
            "wheel_pages": se.MAX_WHEEL_PAGES,
            "cooldown_seconds": se.COOLDOWN_RANGE,
            "chance_percent": se.CHANCE_RANGE,
            "low_health_threshold": se.THRESHOLD_RANGE,
            "spells_per_trigger": se.MAX_TRIGGER_SPELLS,
        },
        "reserved_ids": sorted(se.RESERVED_IDS),
        "settings": se.SETTINGS_DEFAULT,
    }
    print(json.dumps(data, indent=2) if args.json else yaml.safe_dump(data, sort_keys=False, width=1000))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for every command."""
    parser = argparse.ArgumentParser(prog="speakeasy-scribe", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    def game(p: argparse.ArgumentParser) -> None:
        p.add_argument("--game-dir", help="WoW client folder that holds WTF (or set SPEAKEASY_GAME_DIR / .scribe.yaml)")
        p.add_argument("--account", help="WTF account folder, when there is more than one")

    p = sub.add_parser("validate", help="check profiles against SpeakEasy's rules")
    p.add_argument("profile", nargs="+", help="YAML files or folders")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("preview", help="write an HTML page showing the scenes as chat")
    p.add_argument("profile", nargs="+")
    p.add_argument("-o", "--out")
    p.set_defaults(func=cmd_preview)

    p = sub.add_parser("apply", help="merge profiles into SpeakEasy.lua (close WoW first)")
    p.add_argument("profile", nargs="+")
    game(p)
    p.add_argument("--out", help="write this file instead of the one in WTF")
    p.add_argument("--replace", action="store_true", help="replace all stored scenes and triggers instead of merging")
    p.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("export", help="turn stored SpeakEasy scenes back into YAML")
    game(p)
    p.add_argument("--file", help="read this SpeakEasy.lua instead of looking in WTF")
    p.add_argument("--realm")
    p.add_argument("--character")
    p.add_argument("--account-wide", action="store_true", help="export the shared (account) scenes")
    p.add_argument("-o", "--out")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("list", help="list accounts and characters in WTF")
    game(p)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("new", help="scaffold a character profile")
    p.add_argument("name")
    p.add_argument("--realm", required=True)
    p.add_argument("--race", default="")
    p.add_argument("--class", dest="klass", default="")
    p.add_argument("--faction", default="")
    p.add_argument("--dir", default="characters")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("reference", help="print channels, events, variables and limits")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_reference)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command line and return the exit code."""
    args = build_parser().parse_args(argv)
    try:
        code: int = args.func(args)
        return code
    except UsageError as exc:
        print(exc, file=sys.stderr)
        return 1
    except (savedvars.PathError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
