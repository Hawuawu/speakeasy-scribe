"""Run SpeakEasy's own clean-up (L.Db.Load) on files this tool writes."""

import shutil
import subprocess  # noqa: S404
from pathlib import Path

import pytest

from speakeasy_scribe import model, savedvars
from tests.conftest import EXAMPLES, write_yaml

UPSTREAM = Path(__file__).parent / "upstream"
LUA = shutil.which("lua5.1") or shutil.which("luajit")

pytestmark = pytest.mark.skipif(LUA is None, reason="needs lua5.1 or luajit")


def speakeasy_load(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    result = subprocess.run(  # noqa: S603
        [LUA, str(UPSTREAM / "harness.lua"), str(UPSTREAM / "SpeakEasy_Db.lua"), str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    before, after = {}, {}
    for line in result.stdout.splitlines():
        label, key, value = line.split(" ", 2)
        (before if label == "BEFORE" else after)[key] = value
    return before, after


@pytest.mark.parametrize("name", ["aelindra", "tomas"])
def test_speakeasy_keeps_character_files(tmp_path, name):
    out = tmp_path / "SpeakEasy.lua"
    savedvars.apply(savedvars.plan(model.load([EXAMPLES / name]), None, out))
    before, after = speakeasy_load(out)
    for key in ("scenes", "triggers", "useOwn"):
        assert after[f"character.{key}"] == before[f"character.{key}"], key
    if name == "aelindra":
        assert after["character.wheelPages"] == before["character.wheelPages"]
    assert after["character.useOwn"] == "true"


def test_speakeasy_keeps_account_file(tmp_path):
    text = (
        "target: account\nsettings: {primeTimeout: 12, targetFallback: lad}\n"
        "scenes:\n  - {name: Ünïcode Zäk, emote: BOW, cooldown: 0, lines: ['" + "é" * 127 + "', {emote: WAVE}, {text: quiet, enabled: false}]}\n"
        "triggers:\n  - {event: SPELL_CAST, scene: ünïcodezäk, spells: [Fireball, {spell: Drink, item: Water}], chance: 0, cooldown: 3600}\n"
        "wheel:\n  - ['emote:DANCE']\n  - []\n"
    )
    profile = model.load([write_yaml(tmp_path / "p.yaml", text)])
    out = tmp_path / "SpeakEasy.lua"
    savedvars.apply(savedvars.plan(profile, None, out))
    before, after = speakeasy_load(out)
    for key in ("scenes", "triggers", "wheelPages"):
        assert after[f"account.{key}"] == before[f"account.{key}"], key
    assert "primeTimeout=12" in after["account.settings"]
    assert 'targetFallback="lad"' in after["account.settings"]
