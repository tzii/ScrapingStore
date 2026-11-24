"""Small stdlib HTTP server for the report (`scrapingstore serve`).

The report is rebuilt from the SQLite ledger on every page load, so a reload shows
the latest saved collection.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from scrapingstore.ledger.database import DatabaseManager
from scrapingstore.report.generator import render_report
from scrapingstore.report.snapshot import ReportSnapshot


def create_server(
    db: DatabaseManager,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    history_runs: int = 12,
) -> ThreadingHTTPServer:
    """Create an HTTP server that renders the report from SQLite on each request."""

    class ReportHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path == "/api/status":
                products, latest = db.get_catalog_snapshot()
                payload = {
                    "products": len(products),
                    "latest_run_id": latest.get("run_id") if latest else None,
                    "latest_status": latest.get("status") if latest else None,
                    "runs_count": len(db.list_runs(limit=100)),
                }
                self._send(
                    200,
                    json.dumps(payload).encode("utf-8"),
                    "application/json; charset=utf-8",
                )
                return

            if path in ("/", "/index.html", "/dashboard.html"):
                products, latest = db.get_catalog_snapshot()
                history = db.get_multi_run_history(limit=history_runs)
                snapshot = ReportSnapshot.from_products(products, run=latest, history=history)
                self._send(200, render_report(snapshot).encode("utf-8"), "text/html; charset=utf-8")
                return

            self._send(404, b"Not Found", "text/plain; charset=utf-8")

    return ThreadingHTTPServer((host, port), ReportHandler)


def serve_report(
    db: DatabaseManager,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
    history_runs: int = 12,
) -> None:
    """Serve the report until Ctrl+C."""
    server = create_server(db, host=host, port=port, history_runs=history_runs)
    url = f"http://{host}:{server.server_address[1]}/"
    if open_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
