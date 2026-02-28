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
GET /api/blame           -- Human vs AI attribution
GET /api/security        -- Security audit
GET /api/deadcode        -- Dead code findings
GET /api/maturity        -- Module maturity scores
GET /api/dna             -- Repo DNA fingerprint
GET /api/story           -- Repo narrative
GET /api/coveragemap     -- Coverage heat map
GET /api/benchmark       -- Performance benchmark suite
GET /api/gitstats        -- Git statistics deep-dive
GET /api/badges          -- Shields.io badge metadata
GET /api/teach/<module>  -- Tutorial for a specific module
GET /api/audit           -- Comprehensive repo audit (Session 16)
GET /api/semver          -- Semantic version analysis (Session 16)
GET /api/predict         -- Predictive session planner (Session 16)
GET /api                 -- List all available endpoints
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
    # Session 13
    "/api/blame": ["blame", "--json"],
    "/api/security": ["security", "--json"],
    "/api/deadcode": ["deadcode", "--json"],
    "/api/coveragemap": ["coveragemap", "--json"],
    # Session 14
    "/api/maturity": ["maturity", "--json"],
    "/api/dna": ["dna", "--json"],
    "/api/story": ["story", "--json"],
    # Session 15
    "/api/benchmark": ["benchmark", "--json"],
    "/api/gitstats": ["gitstats", "--json"],
    "/api/badges": ["badges", "--json"],
    # Session 16
    "/api/audit": ["audit", "--json"],
    "/api/semver": ["semver", "--json"],
    "/api/predict": ["predict", "--json"],
}

PARAMETERIZED_ROUTES: dict[str, tuple[str, list[str]]] = {
    r"/api/replay/(\d+)": ("replay", ["--json", "--session"]),
    r"/api/diff/(\d+)": ("diff", ["--json", "--session"]),
    r"/api/teach/([a-zA-Z0-9_]+)": ("teach", ["--json"]),
}


class NightshiftHandler(BaseHTTPRequestHandler):
    """HTTP request handler that dispatches to nightshift CLI commands."""

    def _run_command(self, cli_args: list[str]) -> str:
        """Run a nightshift CLI command and return the JSON portion of stdout."""
        repo = getattr(self.server, "repo_path", Path("."))
        result = subprocess.run(
            [sys.executable, "-m", "src.cli"] + cli_args,
            capture_output=True,
            text=True,
            cwd=str(repo),
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or "Command failed")
        output = result.stdout
        for i, ch in enumerate(output):
            if ch in ("{", "["):
                return output[i:]
        return output

    def _send_json(self, code: int, body: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_OPTIONS(self) -> None:
        self._send_json(204, "")

    def do_GET(self) -> None:
        # Strip query string for routing
        path = self.path.split("?")[0]

        # Static routes
        if path in ROUTE_MAP:
            try:
                output = self._run_command(ROUTE_MAP[path])
                self._send_json(200, output)
            except Exception as exc:
                self._send_json(500, json.dumps({"error": str(exc)}))
            return

        # Parameterized routes
        for pattern, (cmd, base_args) in PARAMETERIZED_ROUTES.items():
            match = re.match(pattern, path)
            if match:
                param = match.group(1)
                try:
                    if cmd == "teach":
                        output = self._run_command([cmd, param] + base_args)
                    else:
                        output = self._run_command([cmd] + base_args + [param])
                    self._send_json(200, output)
                except Exception as exc:
                    self._send_json(500, json.dumps({"error": str(exc)}))
                return

        # Sessions list
        if path == "/api/sessions":
            try:
                from src.stats import compute_stats
                repo = getattr(self.server, "repo_path", Path("."))
                stats = compute_stats(repo_path=repo, log_path=repo / "NIGHTSHIFT_LOG.md")
                self._send_json(200, json.dumps({
                    "sessions": stats.to_dict().get("sessions", []),
                    "total": len(stats.sessions),
                }))
            except Exception as exc:
                self._send_json(500, json.dumps({"error": str(exc)}))
            return

        # API index
        if path in ("/api", "/api/"):
            endpoints = sorted(list(ROUTE_MAP.keys()) + ["/api/sessions",
                                                          "/api/replay/<n>",
                                                          "/api/diff/<n>",
                                                          "/api/teach/<module>"])
            self._send_json(200, json.dumps({"endpoints": endpoints, "total": len(endpoints)}))
            return

        self._send_json(404, json.dumps({"error": "Not found"}))

    def log_message(self, format: str, *args) -> None:
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
