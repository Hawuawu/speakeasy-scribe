from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples" / "characters"


@pytest.fixture
def game(tmp_path):
    """A fake WoW client folder with one account and two characters."""
    wtf = tmp_path / "WoW" / "WTF"
    (wtf / "Account" / "ACC" / "SavedVariables").mkdir(parents=True)
    for name in ("Aelindra", "Tomas"):
        (wtf / "Account" / "ACC" / "Argent Dawn" / name / "SavedVariables").mkdir(parents=True)
    return tmp_path / "WoW"


def write_yaml(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path
