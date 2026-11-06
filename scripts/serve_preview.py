"""Render previews for profile folders and serve them locally with hardened headers (used by the DAST scan).

python scripts/serve_preview.py [--port 4173] examples/characters/*
"""

from __future__ import annotations

import argparse
import html
import http.server
from pathlib import Path

from speakeasy_scribe import model, preview

HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Embedder-Policy": "require-corp",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cache-Control": "no-store",
}


def build(folders: list[str]) -> dict[str, bytes]:
    pages: dict[str, bytes] = {}
    links = []
    for folder in folders:
        name = Path(folder).name
        pages[f"/{name}.html"] = preview.render(model.load([folder])).encode("utf-8")
        links.append(f'<li><a href="/{html.escape(name)}.html">{html.escape(name)}</a></li>')
    pages["/"] = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Previews</title></head>'
        f"<body><h1>SpeakEasy previews</h1><ul>{''.join(links)}</ul></body></html>"
    ).encode()
    return pages


def handler(pages: dict[str, bytes]) -> type[http.server.BaseHTTPRequestHandler]:
    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "preview"
        sys_version = ""

        def do_HEAD(self) -> None:  # noqa: N802
            self.do_GET(head=True)

        def do_GET(self, head: bool = False) -> None:  # noqa: N802
            body = pages.get(self.path.split("?", 1)[0])
            status = 200 if body is not None else 404
            body = body if body is not None else b"not found"
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8" if status == 200 else "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            for key, value in HEADERS.items():
                self.send_header(key, value)
            self.end_headers()
            if not head:
                self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folders", nargs="+")
    parser.add_argument("--port", type=int, default=4173)
    args = parser.parse_args()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler(build(args.folders)))
    print(f"previews on http://localhost:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
