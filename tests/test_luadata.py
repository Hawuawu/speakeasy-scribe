import pytest
from hypothesis import given
from hypothesis import strategies as st

from speakeasy_scribe import luadata

WOW_FILE = b"""
SpeakEasyDB = {
\t["version"] = 1,
\t["scenes"] = {
\t\t{
\t\t\t["name"] = "Tavern",
\t\t\t["lines"] = {
\t\t\t\t{
\t\t\t\t\t["text"] = "Say \\"hi\\"\\n",
\t\t\t\t\t["enabled"] = true,
\t\t\t\t}, -- [1]
\t\t\t},
\t\t\t["icon"] = 134400,
\t\t\t["cooldown"] = 2.5,
\t\t}, -- [1]
\t},
\t["settings"] = {
\t\t["window"] = {
\t\t},
\t\t["minimapAngle"] = -45,
\t\t["triggersMuted"] = false,
\t},
}
SpeakEasyCharDB = nil
"""


def test_reads_wow_layout():
    data = luadata.loads(WOW_FILE)
    db = data["SpeakEasyDB"]
    assert db["version"] == 1
    scene = db["scenes"][0]
    assert scene["lines"][0] == {"text": 'Say "hi"\n', "enabled": True}
    assert scene["cooldown"] == 2.5
    assert db["settings"]["window"] == {}
    assert db["settings"]["minimapAngle"] == -45
    assert data["SpeakEasyCharDB"] is None


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("x = 'single'", "single"),
        ("x = [[long\nstring]]", "long\nstring"),
        ("x = [==[a]]b]==]", "a]]b"),
        ("x = '\\65\\066'", "AB"),
        ("x = '\\x41'", "A"),
        ("x = '\\u{e9}'", "é"),
        ("x = 'a\\z   b'", "ab"),
        ("x = 0x10", 16),
        ("x = 1e3", 1000.0),
        ("x = -2", -2),
        ("x = math.huge", float("inf")),
        ("x = { 1, 2, [4] = 4 }", {1: 1, 2: 2, 4: 4}),
        ("x = { a = 1; b = 2 }", {"a": 1, "b": 2}),
        ("-- comment\nx = --[[ block ]] true", True),
        ("x = 'é'", "é"),
    ],
)
def test_values(source, expected):
    assert luadata.loads(source)["x"] == expected


@pytest.mark.parametrize(
    "source",
    [
        "x = os.execute('rm -rf /')",
        "x = function() end",
        "x = 1 + 1",
        "x = { a = b }",
        "x = 'unterminated",
        "x = { 1, 2",
        "local x = 1",
        "x = [[never closed",
    ],
)
def test_rejects_code(source):
    with pytest.raises(luadata.LuaDataError):
        luadata.loads(source)


def test_round_trip_wow_file():
    data = luadata.loads(WOW_FILE)
    assert luadata.loads(luadata.dumps(data)) == data


def test_dumps_escapes_and_lists():
    text = luadata.dumps({"X": {"list": ['a"b', "c\\d", "é\n"], "empty": {}, "num": 1.5, "flag": False}})
    assert luadata.loads(text) == {"X": {"list": ['a"b', "c\\d", "é\n"], "empty": {}, "num": 1.5, "flag": False}}
    assert "-- [1]" in text


scalars = st.one_of(st.booleans(), st.integers(-(2**31), 2**31), st.text(max_size=20))
values = st.recursive(
    scalars,
    lambda children: st.one_of(
        st.lists(children, min_size=1, max_size=4), st.dictionaries(st.from_regex(r"[a-zA-Z_]\w{0,8}", fullmatch=True), children, max_size=4)
    ),
    max_leaves=12,
)


@given(values)
def test_round_trip_property(value):
    assert luadata.loads(luadata.dumps({"V": value}))["V"] == value
