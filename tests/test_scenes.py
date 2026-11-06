import pytest

from speakeasy_scribe.issues import Report
from speakeasy_scribe.scenes import Line, Scene, Spell, Trigger, Wheel, derive_id


@pytest.fixture
def report():
    return Report()


def messages(report):
    return [issue.message for issue in report.issues]


def resolver(*ids):
    return lambda ref: ref if ref in ids else None


def test_scope_number_and_flag(report):
    scope = report.at("here")
    assert scope.number(None, "n", (0, 10), 5) == 5
    assert scope.number("x", "n", (0, 10), 5) == 5
    assert scope.number(True, "n", (0, 10), 5) == 5
    assert scope.number(20, "n", (0, 10), 5) == 20
    assert scope.flag("yes") is True
    assert scope.flag(False) is False
    assert messages(report) == ["n must be a number", "n must be a number", "n must be between 0 and 10", "enabled must be true or false"]
    assert report.errors == report.issues and report.warnings == []
    assert str(report.issues[0]) == "error: here: n must be a number"
    assert scope.child(" line 1").where == "here line 1"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Hello", Line("Hello")),
        ({"emote": "BOW"}, Line("", "BOW")),
        ({"text": "Hi", "emote": "WAVE", "enabled": False}, Line("Hi", "WAVE", False)),
    ],
)
def test_line_parse(report, raw, expected):
    assert Line.parse(raw, report.at("l")) == expected
    assert report.issues == []


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (42, "line must be text"),
        ({"targetName": None}, "must be quoted"),
        ({"text": 5}, "quoted string"),
        ("", "neither text nor an emote"),
        ({"text": "a", "emote": "bow"}, "upper-case emote"),
    ],
)
def test_line_parse_errors(report, raw, message):
    Line.parse(raw, report.at("l"))
    assert any(message in m for m in messages(report))


def test_line_yaml_and_variables():
    assert Line("Hi").to_yaml() == "Hi"
    assert Line("", "BOW").to_yaml() == {"emote": "BOW"}
    assert Line("Hi", None, False).to_yaml() == {"text": "Hi", "enabled": False}
    assert Line("Hello {targetName} in {zone}").variables == {"targetName", "zone"}
    assert Line.from_speakeasy({"text": "x", "emote": "BOW", "enabled": False}) == Line("x", "BOW", False)


def test_scene_parse_and_round_trip(report):
    raw = {"name": " Battle Cry ", "channel": "YELL", "cooldown": 5, "emote": "ROAR", "macro_name": "cry", "lines": ["For the Alliance!"]}
    scene = Scene.parse(raw, report.at("s"), set())
    assert report.issues == []
    assert scene.id == "battlecry" and scene.name == "Battle Cry" and scene.where == "s ' Battle Cry '"
    stored = scene.to_speakeasy()
    assert list(stored) == ["id", "name", "icon", "channel", "defaultEmote", "cooldown", "enabled", "macroName", "lines"]
    again = Scene.from_speakeasy(stored)
    assert again == scene
    assert again.to_yaml() == {
        "id": "battlecry",
        "name": "Battle Cry",
        "channel": "YELL",
        "cooldown": 5,
        "emote": "ROAR",
        "macro_name": "cry",
        "lines": ["For the Alliance!"],
    }


def test_scene_ids_are_unique_and_lines_checked(report):
    taken = set()
    Scene.parse({"name": "A", "lines": ["x"]}, report.at("1"), taken)
    Scene.parse({"name": "a", "lines": "x"}, report.at("2"), taken)
    assert taken == {"a"}
    assert messages(report) == ["id 'a' is used by another scene; set a different id", "lines must be a list", "scene has no enabled lines"]
    assert Scene.parse("nope", report.at("3"), taken) is None
    assert derive_id("!!!") == "scene"


def test_trigger_parse(report):
    scope = report.at("t")
    trigger = Trigger.parse({"event": "SPELL_CAST", "scene": "a", "spells": ["Fireball", {"spell": "Drink", "item": "Water"}]}, scope, resolver("a"))
    assert trigger.spells == (Spell("Fireball"), Spell("Drink", "Water"))
    assert trigger.to_speakeasy()["options"] == {"threshold": 30, "spells": [{"spell": "Fireball"}, {"spell": "Drink", "item": "Water"}]}
    assert Trigger.from_speakeasy(trigger.to_speakeasy()) == trigger
    assert trigger.to_yaml()["spells"] == ["Fireball", {"spell": "Drink", "item": "Water"}]
    low = Trigger.parse({"event": "LOW_HEALTH", "scene": "b", "threshold": 20, "enabled": False}, scope, resolver())
    assert low.to_yaml() == {"event": "LOW_HEALTH", "scene": "b", "chance": 30, "cooldown": 60, "threshold": 20, "enabled": False}
    assert messages(report) == ["scene 'b' is not in this profile; it must already exist in SpeakEasy"]


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ([], "trigger must be a mapping"),
        ({"event": "PARTY_JOIN", "scene": "a"}, "no other triggers"),
        ({"event": "MOUNT", "scene": "Not An Id"}, "not found"),
        ({"event": "MOUNT", "scene": "a", "threshold": 10}, "only matters for LOW_HEALTH"),
        ({"event": "SPELL_CAST", "scene": "a", "spells": "Fireball"}, None),
        ({"event": "SPELL_CAST", "scene": "a", "spells": [{"item": "x"}]}, "each spell must be a name"),
        ({"event": "SPELL_CAST", "scene": "a", "spells": ["x" * 65]}, "limited to 64 bytes"),
        ({"event": "SPELL_CAST", "scene": "a", "spells": [f"s{i}" for i in range(51)]}, "at most 50 spells"),
    ],
)
def test_trigger_problems(report, raw, message):
    Trigger.parse(raw, report.at("t"), resolver("a"))
    if message is None:
        assert report.issues == []
    else:
        assert any(message in m for m in messages(report))


def test_wheel(report):
    wheel = Wheel.parse([["a", "emote:BOW", None, "missing"]], report.at("wheel"), resolver("a"))
    assert wheel.to_speakeasy() == [["a", "emote:BOW", "", "", "", "", "", ""]]
    assert messages(report) == ["slot 'missing' is not a scene in this profile or emote:TOKEN"]
    assert report.issues[0].where == "wheel page 1"
    assert Wheel.parse("a", report.at("wheel"), resolver()) is None
    Wheel.parse([["a"] * 9] * 10, report.at("wheel"), resolver("a"))
    assert "wheel needs 1 to 9 pages" in messages(report) and "a page has 8 slots" in messages(report)
    scenes = [Scene(str(i), str(i)) for i in range(10)]
    assert Wheel.first_scenes(scenes).pages == (tuple(str(i) for i in range(8)),)
