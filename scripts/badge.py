"""Write coverage.svg and tests.svg: python scripts/badge.py coverage.json pytest.log <out dir>"""

import json
import re
import sys
from html import escape
from pathlib import Path


def badge(label: str, message: str, color: str) -> str:
    lw, mw = (round(len(t) * 6.6 + 12) for t in (label, message))
    label, message = escape(label), escape(message)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{lw + mw}" height="20" role="img" aria-label="{label}: {message}">\n'
        '<linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>\n'
        f'<clipPath id="r"><rect width="{lw + mw}" height="20" rx="3" fill="#fff"/></clipPath>\n'
        f'<g clip-path="url(#r)"><rect width="{lw}" height="20" fill="#555"/><rect x="{lw}" width="{mw}" height="20" fill="{color}"/>'
        f'<rect width="{lw + mw}" height="20" fill="url(#s)"/></g>\n'
        '<g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">\n'
        f'<text x="{lw / 2}" y="14">{label}</text><text x="{lw + mw / 2}" y="14">{message}</text></g></svg>\n'
    )


coverage_json, pytest_log, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
pct = round(json.loads(coverage_json.read_text())["totals"]["percent_covered"], 1)
passed = re.findall(r"(\d+) passed", pytest_log.read_text())[-1]
color = "#4c1" if pct >= 90 else "#dfb317" if pct >= 75 else "#e05d44"
out.mkdir(parents=True, exist_ok=True)
(out / "coverage.svg").write_text(badge("coverage", f"{pct}%", color), encoding="utf-8")
(out / "tests.svg").write_text(badge("tests", f"{passed} passed", "#4c1"), encoding="utf-8")
(out / "summary.txt").write_text(f"coverage {pct}%, tests {passed} passed", encoding="utf-8")
