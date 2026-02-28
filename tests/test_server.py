"""Tests for src/server.py — the Nightshift dashboard API server.

Extends original tests with coverage for all Session 15 endpoints.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from http.server import HTTPServer
from io import BytesIO

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.server import NightshiftHandler, ROUTE_MAP, PARAMETERIZED_ROUTES


class MockRequest:
    def __init__(self, path: str):
        self.path = path

    def makefile(self, *args, **kwargs):
        return BytesIO()


def make_handler(path: str) -> NightshiftHandler:
    handler = NightshiftHandler.__new__(NightshiftHandler)
    handler.path = path
    handler.headers = {}
    handler.command = "GET"
    handler.request_version = "HTTP/1.1"
    handler._headers_buffer = []
    handler.wfile = BytesIO()
    handler.requestline = f"GET {path} HTTP/1.1"
    handler.client_address = ("127.0.0.1", 0)
    handler.server = MagicMock()
    handler.server.repo_path = Path(".")
    return handler


class TestRouteMatching:
    def test_unknown_route_returns_404(self):
        handler = make_handler("/api/unknown")
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.do_GET()
        handler.send_response.assert_called_with(404)

    def test_api_health_route_exists(self):
        handler = make_handler("/api/health")
        with patch.object(handler, '_run_command', return_value='{"score": 90}') as mock_run:
            handler.send_response = MagicMock()
            handler.send_header = MagicMock()
            handler.end_headers = MagicMock()
            handler.do_GET()
            mock_run.assert_called_once()
            handler.send_response.assert_called_with(200)

    def test_api_stats_route_exists(self):
        handler = make_handler("/api/stats")
        with patch.object(handler, '_run_command', return_value='{"nights": 10}') as mock_run:
            handler.send_response = MagicMock()
            handler.send_header = MagicMock()
            handler.end_headers = MagicMock()
            handler.do_GET()
            mock_run.assert_called_once()
            handler.send_response.assert_called_with(200)

    def test_cors_headers_present(self):
        handler = make_handler("/api/stats")
        headers_sent = {}
        def mock_send_header(key, val):
            headers_sent[key] = val
        with patch.object(handler, '_run_command', return_value='{}'):
            handler.send_response = MagicMock()
            handler.send_header = mock_send_header
            handler.end_headers = MagicMock()
            handler.do_GET()
        assert "Access-Control-Allow-Origin" in headers_sent


class TestSession15Routes:
    def _test_route(self, path: str, fake_json: str = "{}"):
        handler = make_handler(path)
        with patch.object(handler, '_run_command', return_value=fake_json) as mock_run:
            handler.send_response = MagicMock()
            handler.send_header = MagicMock()
            handler.end_headers = MagicMock()
            handler.do_GET()
            mock_run.assert_called_once()
            handler.send_response.assert_called_with(200)

    def test_benchmark_route(self):
        self._test_route("/api/benchmark", '{"results": []}')

    def test_gitstats_route(self):
        self._test_route("/api/gitstats", '{"total_commits": 50}')

    def test_badges_route(self):
        self._test_route("/api/badges", '{"badges": []}')

    def test_blame_route(self):
        self._test_route("/api/blame", '{"ai_pct": 95}')

    def test_security_route(self):
        self._test_route("/api/security", '{"grade": "A"}')

    def test_deadcode_route(self):
        self._test_route("/api/deadcode", '{"items": []}')

    def test_maturity_route(self):
        self._test_route("/api/maturity", '{"avg_score": 75}')

    def test_dna_route(self):
        self._test_route("/api/dna", '{"hex_digest": "abc12345"}')

    def test_story_route(self):
        self._test_route("/api/story", '{"total_sessions": 15}')

    def test_coveragemap_route(self):
        self._test_route("/api/coveragemap", '{"avg_score": 60}')


class TestParameterizedRoutes:
    def test_replay_route(self):
        handler = make_handler("/api/replay/5")
        with patch.object(handler, '_run_command', return_value='{"session": 5}') as mock_run:
            handler.send_response = MagicMock()
            handler.send_header = MagicMock()
            handler.end_headers = MagicMock()
            handler.do_GET()
            mock_run.assert_called_once()
            handler.send_response.assert_called_with(200)

    def test_diff_route(self):
        handler = make_handler("/api/diff/3")
        with patch.object(handler, '_run_command', return_value='{"files": []}') as mock_run:
            handler.send_response = MagicMock()
            handler.send_header = MagicMock()
            handler.end_headers = MagicMock()
            handler.do_GET()
            mock_run.assert_called_once()
            handler.send_response.assert_called_with(200)

    def test_teach_route(self):
        handler = make_handler("/api/teach/health")
        with patch.object(handler, '_run_command', return_value='{"module": "health"}') as mock_run:
            handler.send_response = MagicMock()
            handler.send_header = MagicMock()
            handler.end_headers = MagicMock()
            handler.do_GET()
            mock_run.assert_called_once()
            handler.send_response.assert_called_with(200)

    def test_replay_route_unknown_session(self):
        handler = make_handler("/api/replay/999")
        with patch.object(handler, '_run_command', side_effect=RuntimeError("session not found")):
            handler.send_response = MagicMock()
            handler.send_header = MagicMock()
            handler.end_headers = MagicMock()
            handler.do_GET()
            handler.send_response.assert_called_with(500)


class TestApiIndex:
    def test_api_index_returns_endpoint_list(self):
        handler = make_handler("/api")
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.do_GET()
        response = handler.wfile.getvalue().decode("utf-8")
        data = json.loads(response)
        assert "endpoints" in data
        assert "total" in data
        assert len(data["endpoints"]) > 10

    def test_api_index_trailing_slash(self):
        handler = make_handler("/api/")
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.do_GET()
        handler.send_response.assert_called_with(200)


class TestRouteMapCompleteness:
    def test_all_session13_routes_present(self):
        assert "/api/blame" in ROUTE_MAP
        assert "/api/security" in ROUTE_MAP
        assert "/api/deadcode" in ROUTE_MAP
        assert "/api/coveragemap" in ROUTE_MAP

    def test_all_session14_routes_present(self):
        assert "/api/maturity" in ROUTE_MAP
        assert "/api/dna" in ROUTE_MAP
        assert "/api/story" in ROUTE_MAP

    def test_all_session15_routes_present(self):
        assert "/api/benchmark" in ROUTE_MAP
        assert "/api/gitstats" in ROUTE_MAP
        assert "/api/badges" in ROUTE_MAP

    def test_teach_in_parameterized_routes(self):
        patterns = list(PARAMETERIZED_ROUTES.keys())
        assert any("teach" in p for p in patterns)

    def test_original_routes_still_present(self):
        for route in ["/api/health", "/api/stats", "/api/coverage",
                      "/api/changelog", "/api/scores", "/api/depgraph",
                      "/api/doctor", "/api/todos", "/api/triage", "/api/plan"]:
            assert route in ROUTE_MAP, f"Missing original route: {route}"


class TestErrorHandling:
    def test_command_error_returns_500(self):
        handler = make_handler("/api/health")
        with patch.object(handler, '_run_command', side_effect=RuntimeError("command failed")):
            handler.send_response = MagicMock()
            handler.send_header = MagicMock()
            handler.end_headers = MagicMock()
            handler.do_GET()
            handler.send_response.assert_called_with(500)

    def test_500_body_has_error_key(self):
        handler = make_handler("/api/stats")
        with patch.object(handler, '_run_command', side_effect=RuntimeError("boom")):
            handler.send_response = MagicMock()
            handler.send_header = MagicMock()
            handler.end_headers = MagicMock()
            handler.do_GET()
        body = handler.wfile.getvalue().decode("utf-8")
        data = json.loads(body)
        assert "error" in data

    def test_options_preflight(self):
        handler = make_handler("/api/health")
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.do_OPTIONS()
        handler.send_response.assert_called_with(204)

    def test_query_string_ignored(self):
        handler = make_handler("/api/stats?refresh=true")
        with patch.object(handler, '_run_command', return_value='{"nights": 15}') as mock_run:
            handler.send_response = MagicMock()
            handler.send_header = MagicMock()
            handler.end_headers = MagicMock()
            handler.do_GET()
            mock_run.assert_called_once()
            handler.send_response.assert_called_with(200)
