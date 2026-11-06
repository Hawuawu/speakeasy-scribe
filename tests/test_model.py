import pytest

from speakeasy_scribe import model
from tests.conftest import EXAMPLES, write_yaml

BASE = """
character: {name: Test, realm: Realm}
"""


def load(tmp_path, text):
    return model.load([write_yaml(tmp_path / "p.yaml", BASE + text)])


def messages(profile, level="error"):
    return [i.message for i in profile.issues if i.level == level]


@pytest.mark.parametrize("name", ["aelindra", "tomas"])
def test_examples_are_clean(name):
    profile = model.load([EXAMPLES / name])
    assert profile.issues == []
    assert profile.scenes


def test_scene_defaults_and_ids(tmp_path):
    profile = load(tmp_path, "scenes:\n  - name: Good Morning!\n    lines: ['Hi']\n")
    scene = profile.scenes[0]
    assert scene["id"] == "goodmorning"
    assert scene["channel"] == "SAY"
    assert scene["icon"] == 134400
    assert scene["cooldown"] == 2
    assert scene["lines"] == [{"text": "Hi", "enabled": True}]
    assert model.to_set(profile)["scenes"][0]["id"] == "goodmorning"


@pytest.mark.parametrize(
    ("yaml_text", "expected"),
    [
        ("scenes:\n  - name: A\n    channel: WHISPER\n    lines: [x]\n", "channel must be one of"),
        ("scenes:\n  - name: Mute\n    lines: [x]\n", "reserved"),
        ("scenes:\n  - {name: A, lines: [x]}\n  - {name: a, lines: [y]}\n", "used by another scene"),
        ("scenes:\n  - {name: A, id: Bad-Id, lines: [x]}\n", "lower-case"),
        ("scenes:\n  - {name: " + "N" * 33 + ", lines: [x]}\n", "longer than 32"),
        ("scenes:\n  - {name: A, lines: ['" + "x" * 256 + "']}\n", "cuts lines at 255"),
        ("scenes:\n  - {name: A, lines: ['a|cffff0000b']}\n", "escape code"),
        ("scenes:\n  - {name: A, lines: [{emote: wave}]}\n", "upper-case emote"),
        ("scenes:\n  - {name: A, lines: [{targetName}]}\n", "must be quoted"),
        ("scenes:\n  - {name: A, lines: [42]}\n", "line must be text"),
        ("scenes:\n  - {name: A, lines: ['']}\n", "neither text nor an emote"),
        ("scenes:\n  - {name: A, cooldown: 5000, lines: [x]}\n", "between 0 and 3600"),
        ("scenes:\n  - {name: A, colour: red, lines: [x]}\n", "unknown scene key"),
        ("scenes:\n  - {lines: [x]}\n", "needs a name"),
        ("scenes:\n  - {name: A, icon: abc, lines: [x]}\n", "texture file ID"),
        ("scenes:\n  - {name: A, macro_name: ThisNameIsWayTooLong, lines: [x]}\n", "macro_name"),
        ("triggers:\n  - {event: PARTY_JOIN, scene: a}\n", "no other triggers"),
        ("scenes: [{name: A, lines: [x]}]\ntriggers:\n  - {event: LOW_HEALTH, scene: a, threshold: 100}\n", "between 1 and 99"),
        ("scenes: [{name: A, lines: [x]}]\ntriggers:\n  - {event: SPELL_CAST, scene: a}\n", "needs a list of spells"),
        ("scenes: [{name: A, lines: [x]}]\ntriggers:\n  - {event: MOUNT, scene: a, spells: [x]}\n", "only apply to SPELL_CAST"),
        ("scenes: [{name: A, lines: [x]}]\ntriggers:\n  - {event: MOUNT, scene: 'No Such'}\n", "not found"),
        ("scenes: [{name: A, lines: [x]}]\ntriggers:\n  - {event: MOUNT, scene: a, chance: 101}\n", "between 0 and 100"),
        ("scenes: [{name: A, lines: [x]}]\nwheel: [[a, nope]]\n", "is not a scene"),
        ("scenes: [{name: A, lines: [x]}]\nwheel: [[a, a, a, a, a, a, a, a, a]]\n", "8 slots"),
        ("wheel: [a]\n", "list of pages"),
        ("settings: {primeTimeout: 100}\n", "between 3 and 60"),
        ("settings: {wheelScale: big}\n", "must be like"),
        ("settings: {nope: 1}\n", "unknown SpeakEasy setting"),
        ("target: guild\n", "target must be"),
        ("use_own: maybe\n", "use_own must be"),
        ("colour: red\n", "unknown key"),
        ("scenes: {a: 1}\n", "must be a list"),
        ("settings: [1]\n", "must be a mapping"),
    ],
)
def test_errors(tmp_path, yaml_text, expected):
    profile = load(tmp_path, yaml_text)
    assert any(expected in m for m in messages(profile)), messages(profile)


def test_party_trigger_is_explained(tmp_path):
    profile = load(tmp_path, "triggers:\n  - {event: PARTY_JOIN, scene: a}\n")
    assert "ENTER_COMBAT" in messages(profile)[0]


@pytest.mark.parametrize(
    ("yaml_text", "expected"),
    [
        ("scenes:\n  - {name: A, lines: ['Hi {target}']}\n", "unknown variable {target}"),
        ("scenes:\n  - {name: A, lines: ['I cast {spellName}']}\n", "only filled by SPELL_CAST"),
        ("scenes:\n  - {name: A, lines: [{text: x, enabled: false}]}\n", "no enabled lines"),
        ("triggers:\n  - {event: MOUNT, scene: stored}\n", "must already exist"),
        ("scenes: [{name: A, lines: [x]}]\ntriggers:\n  - {event: MOUNT, scene: a, threshold: 20}\n", "only matters for LOW_HEALTH"),
    ],
)
def test_warnings(tmp_path, yaml_text, expected):
    profile = load(tmp_path, yaml_text)
    assert not profile.errors
    assert any(expected in m for m in messages(profile, "warning")), profile.issues


def test_character_needs_name_and_realm(tmp_path):
    profile = model.load([write_yaml(tmp_path / "p.yaml", "scenes: []\n")])
    assert any("character.name" in m for m in messages(profile))
    profile = model.load([write_yaml(tmp_path / "p.yaml", "target: account\nscenes: []\n")])
    assert profile.errors == []


def test_files_merge_and_conflict(tmp_path):
    a = write_yaml(tmp_path / "a.yaml", BASE + "wheel: [[a]]\nscenes: [{name: A, lines: [x]}]\n")
    b = write_yaml(tmp_path / "b.yaml", "character: {name: Other}\nwheel: [[a]]\nscenes: [{name: B, lines: [y]}]\n")
    profile = model.load([a, b])
    assert [s["id"] for s in profile.scenes] == ["a", "b"]
    assert any("differs" in m for m in messages(profile))
    assert any("already set" in m for m in messages(profile))


def test_bad_files(tmp_path):
    assert model.load([tmp_path / "missing.yaml"]).errors
    assert model.load([write_yaml(tmp_path / "list.yaml", "- 1\n")]).errors
    assert model.load([write_yaml(tmp_path / "bad.yaml", "a: [\n")]).errors
    assert model.load([tmp_path]).errors  # folder with only broken files is still read
    empty = tmp_path / "empty"
    empty.mkdir()
    assert any("no YAML" in i.message for i in model.load([empty]).errors)


def test_spell_trigger_and_round_trip(tmp_path):
    profile = load(
        tmp_path,
        "scenes: [{name: Cast, emote: BOW, cooldown: 5, enabled: false, macro_name: Cast, icon: 1,"
        " lines: [x, {text: y, enabled: false}, {emote: WAVE}]}]\n"
        "triggers:\n  - {event: SPELL_CAST, scene: Cast, spells: [Fireball, {spell: Drink, item: Water}], enabled: false}\n"
        "  - {event: LOW_HEALTH, scene: cast, threshold: 20}\n"
        "wheel: [[cast, 'emote:DANCE']]\n",
    )
    assert profile.issues == []
    data = model.to_set(profile)
    assert data["triggers"][0]["options"]["spells"] == [{"spell": "Fireball"}, {"spell": "Drink", "item": "Water"}]
    assert data["wheelPages"] == [["cast", "emote:DANCE", "", "", "", "", "", ""]]
    exported = model.from_set(data, {"name": "Test", "realm": "Realm"})
    again = model.load([write_yaml(tmp_path / "again.yaml", __import__("yaml").safe_dump(exported))])
    assert again.issues == []
    assert model.to_set(again) == data


def test_from_set_tolerates_odd_shapes():
    out = model.from_set({"scenes": {1: {"id": "a", "name": "A", "lines": {}}}, "triggers": "bad"})
    assert out["scenes"][0]["lines"] == []
    assert out["triggers"] == []
