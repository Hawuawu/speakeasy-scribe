import json

import pytest

from speakeasy_scribe import cli, luadata
from tests.conftest import EXAMPLES, write_yaml

AELINDRA = str(EXAMPLES / "aelindra")


def run(capsys, *args):
    code = cli.main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def test_validate(capsys, tmp_path):
    assert run(capsys, "validate", AELINDRA)[0] == 0
    bad = write_yaml(tmp_path / "bad.yaml", "scenes: [{name: Mute, lines: [x]}]\n")
    code, out, err = run(capsys, "validate", str(bad))
    assert code == 1 and "reserved" in err
    code, out, _ = run(capsys, "validate", "--json", str(bad))
    assert code == 1 and json.loads(out)["ok"] is False
    assert run(capsys, "validate", "--json", AELINDRA)[0] == 0


def test_preview(capsys, tmp_path, monkeypatch):
    out_file = tmp_path / "p.html"
    assert run(capsys, "preview", AELINDRA, "-o", str(out_file))[0] == 0
    assert "Aelindra" in out_file.read_text(encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert run(capsys, "preview", AELINDRA)[0] == 0
    assert (tmp_path / "aelindra-preview.html").exists()


def test_apply_dry_run_then_write_and_export(capsys, game, tmp_path):
    target = game / "WTF" / "Account" / "ACC" / "Argent Dawn" / "Aelindra" / "SavedVariables" / "SpeakEasy.lua"
    code, out, _ = run(capsys, "apply", AELINDRA, "--game-dir", str(game), "--dry-run")
    assert code == 0 and "would write" in out and not target.exists()
    code, out, _ = run(capsys, "apply", AELINDRA, "--game-dir", str(game))
    assert code == 0 and target.exists()
    code, out, _ = run(capsys, "apply", AELINDRA, "--game-dir", str(game))
    assert "backup:" in out

    code, out, _ = run(capsys, "export", "--game-dir", str(game), "--realm", "argent dawn", "--character", "aelindra")
    assert code == 0 and "name: Aelindra" in out and "realm: Argent Dawn" in out
    exported = tmp_path / "exported.yaml"
    assert run(capsys, "export", "--file", str(target), "-o", str(exported))[0] == 0
    assert run(capsys, "validate", str(exported))[1].count("errors") == 1

    code, out, _ = run(capsys, "list", "--game-dir", str(game))
    assert "Aelindra: own scenes" in out and "Tomas: no file" in out


def test_apply_env_and_errors(capsys, game, tmp_path, monkeypatch):
    bad = write_yaml(tmp_path / "bad.yaml", "scenes: [{name: Mute, lines: [x]}]\n")
    assert run(capsys, "apply", str(bad), "--game-dir", str(game))[0] == 1
    code, _, err = run(capsys, "apply", AELINDRA)
    monkeypatch.delenv("SPEAKEASY_GAME_DIR", raising=False)
    assert code == 1 and "error:" in err
    monkeypatch.setenv("SPEAKEASY_GAME_DIR", str(game))
    assert run(capsys, "apply", str(EXAMPLES / "tomas"))[0] == 0
    code, _, err = run(capsys, "apply", AELINDRA, "--game-dir", str(tmp_path / "nowhere"))
    assert code == 1 and "WTF" in err
    out = tmp_path / "x.lua"
    assert run(capsys, "apply", AELINDRA, "--out", str(out))[0] == 0
    assert "SpeakEasyCharDB" in luadata.loads(out.read_bytes())


def test_config_file(capsys, game, tmp_path, monkeypatch):
    monkeypatch.delenv("SPEAKEASY_GAME_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".scribe.yaml").write_text(f"game_dir: '{game}'\naccount: ACC\n", encoding="utf-8")
    assert run(capsys, "apply", AELINDRA)[0] == 0
    (tmp_path / ".scribe.yaml").write_text("- not a mapping\n", encoding="utf-8")
    assert cli._config() == {}


def test_export_errors(capsys, game, tmp_path, monkeypatch):
    monkeypatch.delenv("SPEAKEASY_GAME_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert run(capsys, "export")[0] == 1
    assert run(capsys, "export", "--game-dir", str(game))[0] == 1
    assert run(capsys, "export", "--game-dir", str(game), "--account-wide")[0] == 1
    account = tmp_path / "account.lua"
    account.write_text(luadata.dumps({"SpeakEasyDB": {"scenes": [{"id": "a", "name": "A", "lines": [{"text": "x"}]}]}}), encoding="utf-8")
    code, out, _ = run(capsys, "export", "--file", str(account))
    assert code == 0 and "target: account" in out
    assert run(capsys, "list")[0] == 1
    code, _, err = run(capsys, "export", "--file", str(write_yaml(tmp_path / "code.lua", "X = os.exit()")))
    assert code == 1 and "only data" in err


def test_new_and_reference(capsys, tmp_path):
    folder = tmp_path / "chars"
    args = ("new", "Mira Brightwood", "--realm", "Argent Dawn", "--race", "Human", "--class", "Priest", "--dir", str(folder))
    assert run(capsys, *args)[0] == 0
    created = folder / "mira-brightwood" / "character.yaml"
    assert "name: Mira Brightwood" in created.read_text(encoding="utf-8")
    assert run(capsys, "validate", str(created))[0] == 0
    assert run(capsys, *args)[0] == 1
    code, out, _ = run(capsys, "reference", "--json")
    assert code == 0 and "TARGET_NPC" in json.loads(out)["events"]
    assert "targetName" in run(capsys, "reference")[1]


def test_version(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert capsys.readouterr().out.strip()
