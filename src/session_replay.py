"""Session replay engine for Awake."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class ReplayConfig:
    """Configuration for session replay."""

    model: str = "gpt-4o-mini"
    speed: float = 1.0
    annotate: bool = True
    max_events: int = 1000
    pause_on_error: bool = True
    output_format: str = "json"  # json | text


@dataclass
class ReplayEvent:
    """A single event in a session replay."""

    index: int
    timestamp: float
    event_type: str  # edit | command | test | error | checkpoint
    file: Optional[str]
    content: Optional[str]
    metadata: dict[str, Any] = field(default_factory=dict)
    annotation: Optional[str] = None


@dataclass
class ReplaySession:
    """A full session replay result."""

    session_id: str
    source_file: str
    total_events: int
    duration_seconds: float
    events: list[ReplayEvent] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    summary: Optional[str] = None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_session_file(path: Path) -> list[dict[str, Any]]:
    """Parse a session JSON file into raw event dicts."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("events", [])
    raise ValueError(f"Unexpected session format in {path}")


def _classify_event(raw: dict[str, Any]) -> str:
    """Classify a raw event dict into an event type."""
    t = raw.get("type", "").lower()
    if t in ("edit", "insert", "delete", "replace"):
        return "edit"
    if t in ("run", "command", "shell", "exec"):
        return "command"
    if t in ("test", "pytest", "unittest"):
        return "test"
    if t in ("error", "exception", "traceback"):
        return "error"
    if t in ("save", "checkpoint", "commit"):
        return "checkpoint"
    return "edit"


def _annotate_event(event: ReplayEvent) -> str:
    """Generate a stub annotation for a replay event."""
    if event.event_type == "edit":
        return f"Edited {event.file or 'unknown file'}"
    if event.event_type == "command":
        return f"Ran command: {(event.content or '')[:60]}"
    if event.event_type == "test":
        return "Executed test suite"
    if event.event_type == "error":
        return f"Error encountered: {(event.content or '')[:80]}"
    if event.event_type == "checkpoint":
        return f"Checkpoint saved"
    return "Event recorded"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SessionReplayEngine:
    """Replays a recorded coding session with optional AI annotations."""

    def __init__(self, config: Optional[ReplayConfig] = None) -> None:
        self.config = config or ReplayConfig()

    def replay(self, session_file: Path) -> dict[str, Any]:
        """Replay the session in *session_file* and return a result dict."""
        raw_events = _parse_session_file(session_file)
        raw_events = raw_events[: self.config.max_events]

        events: list[ReplayEvent] = []
        errors: list[dict[str, Any]] = []
        start_ts: Optional[float] = None

        for i, raw in enumerate(raw_events):
            ts = float(raw.get("timestamp", i))
            if start_ts is None:
                start_ts = ts

            event_type = _classify_event(raw)
            event = ReplayEvent(
                index=i,
                timestamp=ts,
                event_type=event_type,
                file=raw.get("file"),
                content=raw.get("content") or raw.get("data"),
                metadata=raw.get("metadata", {}),
            )

            if self.config.annotate:
                event.annotation = _annotate_event(event)

            if event_type == "error":
                errors.append({"index": i, "timestamp": ts, "content": event.content})
                if self.config.pause_on_error:
                    # In a real replay we'd pause here
                    pass

            events.append(event)

        end_ts = float(raw_events[-1].get("timestamp", len(raw_events) - 1)) if raw_events else 0.0
        duration = (end_ts - (start_ts or 0.0)) / max(self.config.speed, 0.01)

        import hashlib
        session_id = hashlib.md5(session_file.read_bytes()).hexdigest()[:12]

        session = ReplaySession(
            session_id=session_id,
            source_file=str(session_file),
            total_events=len(events),
            duration_seconds=round(duration, 2),
            events=events,
            errors=errors,
            summary=f"Replayed {len(events)} events with {len(errors)} error(s).",
        )

        return {
            "session_id": session.session_id,
            "source_file": session.source_file,
            "total_events": session.total_events,
            "duration_seconds": session.duration_seconds,
            "error_count": len(errors),
            "summary": session.summary,
            "events": [
                {
                    "index": e.index,
                    "timestamp": e.timestamp,
                    "type": e.event_type,
                    "file": e.file,
                    "annotation": e.annotation,
                }
                for e in events
            ],
        }
