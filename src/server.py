"""HTTP API server for the Nightshift dashboard.

Wraps CLI commands as JSON HTTP endpoints.  Uses only stdlib
(http.server + subprocess) to maintain the zero-dependency principle.

Endpoints
---------
GET /api/health          -- Code health report
GET /api/stats           -- Repository statistics
GET /api/coverage        -- Test coverage trend
GET /api/changelog       -- Changelog entries
GET /api/scores          -- PR quality scores
GET /api/depgraph        -- Module dependency graph
GET /api/doctor          -- Repo diagnostics
GET /api/todos           -- Stale TODO annotations
GET /api/triage          -- Issue triage
GET /api/plan            -- Brain task ranking
GET /api/sessions        -- List available sessions
GET /api/replay/<n>      -- Replay session N
GET /api/diff/<n>        -- Diff for session N
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional


ROUTE_MAP: dict[str, list[str]] = {
    "/api/health": ["health", "--json"],
    "/api/stats": ["stats", "--json"],
    "/api/coverage": ["coverage", "--json"],
    "/api/changelog": ["changelog", "--json"],
    "/api/scores": ["score", "--json"],
    "/api/depgraph": ["depgraph", "--json"],
    "/api/doctor": ["doctor", "--json"],
    "/api/todos": ["todos", "--json"],
    "/api/triage": ["triage", "--json"],
    "/api/plan": ["plan", "--json"],
}

PARAMETERIZED_ROUTES: dict[str, tuple[str, list[str]]] = {
    r"/api/replay/(\d+)": ("replay", ["--json", "--session"]),
    r"/api/diff/(\d+)": ("diff", ["--json", "--session"]),
}


class NightshiftHandler(BaseHTTPRequestHandler):
    """HTTP request handler that dispatches to nightshift CLI commands."""

    def _run_command(self, cli_args: list[str]) -> str:
        """Run a nightshift CLI command and return stdout."""
        repo = getattr(self.server, "repo_path", Path("."))
        result = subprocess.run(
            [sys.executable, "-m", "src.cli"] + cli_args,
            capture_output=True,
            text=True,
            cwd=str(repo),
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or "Command failed")
        return result.stdout

    def _send_json(self, code: int, body: str) -> None:
        """Send a JSON response with CORS headers."""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests."""
        self._send_json(204, "")

    def do_GET(self) -> None:
        """Route GET requests to CLI commands."""
        # Static routes
        if self.path in ROUTE_MAP:
            try:
                output = self._run_command(ROUTE_MAP[self.path])
                self._send_json(200, output)
            except Exception as exc:
                self._send_json(500, json.dumps({"error": str(exc)}))
            return

        # Parameterized routes
        for pattern, (cmd, base_args) in PARAMETERIZED_ROUTES.items():
            match = re.match(pattern, self.path)
            if match:
                session_num = match.group(1)
                try:
                    output = self._run_command([cmd] + base_args + [session_num])
                    self._send_json(200, output)
                except Exception as exc:
                    self._send_json(500, json.dumps({"error": str(exc)}))
                return

        # Sessions list (derived from stats)
        if self.path == "/api/sessions":
            try:
                from src.stats import compute_stats
                repo = getattr(self.server, "repo_path", Path("."))
                stats = compute_stats(
                    repo_path=repo, log_path=repo / "NIGHTSHIFT_LOG.md"
                )
                self._send_json(200, json.dumps({
                    "sessions": stats.to_dict().get("sessions", []),
                    "total": len(stats.sessions),
                }))
            except Exception as exc:
                self._send_json(500, json.dumps({"error": str(exc)}))
            return

        # 404
        self._send_json(404, json.dumps({"error": "Not found"}))

    def log_message(self, format: str, *args) -> None:
        """Suppress default logging to stderr."""
        pass


def start_server(
    port: int = 8710,
    repo_path: Optional[Path] = None,
    open_browser: bool = True,
) -> None:
    """Start the dashboard API server."""
    server = HTTPServer(("127.0.0.1", port), NightshiftHandler)
    server.repo_path = repo_path or Path(__file__).resolve().parent.parent
    print(f"Nightshift API server running on http://127.0.0.1:{port}")
    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()
