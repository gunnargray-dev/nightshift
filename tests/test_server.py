"""Tests for src/server.py — the Nightshift dashboard API server."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from http.server import HTTPServer
from io import BytesIO

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.server import NightshiftHandler


class MockRequest:
    """Minimal mock for an HTTP request."""

    def __init__(self, path: str):
        self.path = path

    def makefile(self, *args, **kwargs):
        return BytesIO()


def make_handler(path: str) -> NightshiftHandler:
    """Create a handler with a mocked request for the given path."""
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
    """Tests that the handler routes to the correct CLI commands."""

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
