import pytest

from speakeasy_scribe import luadata, model, savedvars
from tests.conftest import EXAMPLES, write_yaml

CHAR_FILE = ("WTF", "Account", "ACC", "Argent Dawn", "Aelindra", "SavedVariables", "SpeakEasy.lua")


def stored(game, *parts):
    return luadata.loads(game.joinpath(*parts).read_bytes())


def test_paths(game, tmp_path):
    wtf = savedvars.wtf_dir(game)
    assert savedvars.wtf_dir(wtf) == wtf
    assert savedvars.character_file(wtf, None, "argent dawn", "AELINDRA") == game.joinpath(*CHAR_FILE)
    assert savedvars.account_file(wtf, "acc").parent.parent.name == "ACC"
    assert len(savedvars.characters(wtf)) == 2
    with pytest.raises(savedvars.PathError):
        savedvars.wtf_dir(tmp_path / "nowhere")
    with pytest.raises(savedvars.PathError):
        savedvars.character_file(wtf, None, "Argent Dawn", "Nobody")
    (wtf / "Account" / "SECOND").mkdir()
    with pytest.raises(savedvars.PathError, match="choose an account"):
        savedvars.account_file(wtf, None)


def test_apply_character_then_merge(game):
    wtf = savedvars.wtf_dir(game)
    profile = model.load([EXAMPLES / "aelindra"])
    first = savedvars.plan(profile, wtf)
    assert first.change.added[0] == "greeting"
    assert savedvars.apply(first) == []
    data = stored(game, *CHAR_FILE)["SpeakEasyCharDB"]
    assert data["useOwn"] is True
    assert [s["id"] for s in data["scenes"]][:2] == ["greeting", "farewell"]

    # Something made in game: a scene and a trigger for it, plus a trigger on a profile scene.
    data["scenes"].append({"id": "ingame", "name": "In game", "lines": [{"text": "hi", "enabled": True}]})
    data["triggers"].append({"event": "MOUNT", "sceneId": "ingame", "chance": 10, "cooldown": 5, "enabled": True, "options": {}})
    game.joinpath(*CHAR_FILE).write_text(luadata.dumps({"SpeakEasyCharDB": data}), encoding="utf-8")

    second = savedvars.plan(profile, wtf)
    assert second.change.replaced[0] == "greeting"
    assert second.change.kept == ["ingame"]
    backups = savedvars.apply(second)
    assert len(backups) == 1 and backups[0].exists()
    data = stored(game, *CHAR_FILE)["SpeakEasyCharDB"]
    assert "ingame" in [s["id"] for s in data["scenes"]]
    assert sum(t["sceneId"] == "ingame" for t in data["triggers"]) == 1
    assert len(data["triggers"]) == 5

    replaced = savedvars.plan(profile, wtf, replace=True)
    assert "ingame" not in [s["id"] for s in replaced.data["scenes"]]


def test_account_target_and_settings(game, tmp_path):
    wtf = savedvars.wtf_dir(game)
    profile = model.load([write_yaml(tmp_path / "a.yaml", "target: account\nsettings: {primeTimeout: 12}\nscenes: [{name: A, lines: [x]}]\n")])
    savedvars.apply(savedvars.plan(profile, wtf))
    data = stored(game, "WTF", "Account", "ACC", "SavedVariables", "SpeakEasy.lua")["SpeakEasyDB"]
    assert data["version"] == 1
    assert data["settings"]["primeTimeout"] == 12


def test_character_settings_go_to_account_file(game, tmp_path):
    wtf = savedvars.wtf_dir(game)
    text = "character: {name: Tomas, realm: Argent Dawn}\nsettings: {targetFallback: lad}\nscenes: [{name: A, lines: [x]}]\n"
    profile = model.load([write_yaml(tmp_path / "t.yaml", text)])
    with pytest.raises(savedvars.PathError, match="log in once"):
        savedvars.plan(profile, wtf)
    account = savedvars.account_file(wtf, None)
    account.write_text(luadata.dumps({"SpeakEasyDB": {"version": 1, "scenes": [], "settings": {"wheelScale": 1.5}}}), encoding="utf-8")
    savedvars.apply(savedvars.plan(profile, wtf))
    settings = luadata.loads(account.read_bytes())["SpeakEasyDB"]["settings"]
    assert settings == {"wheelScale": 1.5, "targetFallback": "lad"}


def test_plan_needs_target(tmp_path):
    profile = model.load([EXAMPLES / "tomas"])
    with pytest.raises(savedvars.PathError):
        savedvars.plan(profile, None)
    out = tmp_path / "out.lua"
    savedvars.apply(savedvars.plan(profile, None, out))
    assert "SpeakEasyCharDB" in luadata.loads(out.read_bytes())


def test_merge_handles_odd_existing_data():
    incoming = {"scenes": [{"id": "a"}], "triggers": []}
    result, change = savedvars.merge({"scenes": {}, "triggers": "x", "wheelPages": [["a"]]}, incoming)
    assert result["scenes"] == [{"id": "a"}] and change.added == ["a"]
    assert result["wheelPages"] == [["a"]]
    result, _ = savedvars.merge({"scenes": {1: {"id": "b"}}}, incoming, replace=True)
    assert result["scenes"] == [{"id": "a"}]
    assert savedvars.read(savedvars.Path("missing.lua"), "X") is None
