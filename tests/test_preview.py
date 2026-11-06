from speakeasy_scribe import model, preview
from tests.conftest import EXAMPLES, write_yaml


def test_preview_shows_chat_wheel_and_triggers():
    page = preview.render(model.load([EXAMPLES / "aelindra"]))
    assert "Aelindra says: Ishnu-alah, Varian." in page
    assert "Ashenvale" in page
    assert "Elune-adore" in page
    assert "page 1" in page and "/dance" in page
    assert "LOW_HEALTH" in page and "below 30% health" in page
    assert "Cat Form" in page
    assert "Validation passed" in page
    assert "Content-Security-Policy" in page and "<script" not in page


def test_preview_flags_and_escapes(tmp_path):
    text = (
        "character: {name: '<b>X</b>', realm: R, personality: brave}\n"
        "scenes:\n  - {name: A, channel: EMOTE, enabled: false, lines: ['grins, \"{target}\" <script>', {text: quiet, enabled: false}]}\n"
        "  - {name: B, lines: ['" + "x" * 300 + "']}\n"
    )
    page = preview.render(model.load([write_yaml(tmp_path / "p.yaml", text)]))
    assert "<script>" not in page and "&lt;script&gt;" in page
    assert "&lt;b&gt;X&lt;/b&gt;" in page
    assert '<span class="var">{target}</span>' in page
    assert 'class="speech"' in page
    assert "bytes over" in page
    assert 'class="off"' in page
    assert "No wheel in this profile" in page
    assert "warning:" in page and "error:" in page
