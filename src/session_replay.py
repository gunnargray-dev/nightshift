"""Session replay utilities for awake."""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional


@dataclass
class ReplayEvent:
    """A single event captured during an awake session."""

    timestamp: datetime
    kind: str  # e.g. 'tool_call', 'llm_response', 'file_write', 'shell_exec'
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReplaySession:
    """A full recorded session."""

    session_id: str
    events: list[ReplayEvent] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _serialize_event(event: ReplayEvent) -> dict:
    return {
        "timestamp": event.timestamp.isoformat(),
        "kind": event.kind,
        "payload": event.payload,
        "metadata": event.metadata,
    }


def _deserialize_event(data: dict) -> ReplayEvent:
    return ReplayEvent(
        timestamp=datetime.fromisoformat(data["timestamp"]),
        kind=data["kind"],
        payload=data.get("payload", {}),
        metadata=data.get("metadata", {}),
    )


def save_session(session: ReplaySession, path: str) -> None:
    """
    Persist a ReplaySession to a JSON file.

    Args:
        session: The session to save.
        path: Output file path.
    """
    payload = {
        "session_id": session.session_id,
        "metadata": session.metadata,
        "events": [_serialize_event(e) for e in session.events],
    }
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_session(path: str) -> ReplaySession:
    """
    Load a ReplaySession from a JSON file.

    Args:
        path: Path to the JSON file.

    Returns:
        A ReplaySession instance.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return ReplaySession(
        session_id=data["session_id"],
        events=[_deserialize_event(e) for e in data.get("events", [])],
        metadata=data.get("metadata", {}),
    )


# ---------------------------------------------------------------------------
# Filtering and slicing
# ---------------------------------------------------------------------------


def filter_events(
    session: ReplaySession,
    kind: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    payload_key: Optional[str] = None,
    payload_value: Optional[Any] = None,
) -> list[ReplayEvent]:
    """
    Return events matching all supplied filters.

    Args:
        session: The session to filter.
        kind: If given, only return events of this kind.
        since: If given, only return events at or after this timestamp.
        until: If given, only return events at or before this timestamp.
        payload_key: If given (with payload_value), filter by payload field.
        payload_value: Required when payload_key is set.

    Returns:
        Filtered list of ReplayEvent objects.
    """
    events = session.events
    if kind:
        events = [e for e in events if e.kind == kind]
    if since:
        events = [e for e in events if e.timestamp >= since]
    if until:
        events = [e for e in events if e.timestamp <= until]
    if payload_key is not None:
        events = [e for e in events if e.payload.get(payload_key) == payload_value]
    return events


def slice_session(
    session: ReplaySession,
    start_index: int = 0,
    end_index: Optional[int] = None,
) -> ReplaySession:
    """
    Return a new ReplaySession containing a slice of the events.

    Args:
        session: The source session.
        start_index: First event index (inclusive).
        end_index: Last event index (exclusive). Defaults to end.

    Returns:
        A new ReplaySession with the sliced events.
    """
    return ReplaySession(
        session_id=session.session_id,
        events=session.events[start_index:end_index],
        metadata=dict(session.metadata),
    )


# ---------------------------------------------------------------------------
# Replay execution
# ---------------------------------------------------------------------------


def iter_events(
    session: ReplaySession,
    *,
    reverse: bool = False,
) -> Iterator[ReplayEvent]:
    """
    Iterate over session events, optionally in reverse.

    Args:
        session: The session to iterate.
        reverse: If True, iterate newest-first.

    Yields:
        ReplayEvent objects.
    """
    events = list(session.events)
    if reverse:
        events = list(reversed(events))
    yield from events


def replay_events(
    session: ReplaySession,
    handler: Any,
    *,
    kind_filter: Optional[str] = None,
    dry_run: bool = False,
) -> list[Any]:
    """
    Replay session events by dispatching each to a handler.

    The handler should be a callable or an object with methods named
    ``handle_<kind>`` (e.g. ``handle_tool_call``).  If neither form
    matches, the event is skipped.

    Args:
        session: The session to replay.
        handler: Callable or object with ``handle_<kind>`` methods.
        kind_filter: If given, only replay events of this kind.
        dry_run: If True, log events without calling the handler.

    Returns:
        List of handler return values.
    """
    results = []
    for event in iter_events(session):
        if kind_filter and event.kind != kind_filter:
            continue

        if dry_run:
            results.append({"dry_run": True, "event": _serialize_event(event)})
            continue

        if callable(handler):
            results.append(handler(event))
        else:
            method_name = f"handle_{event.kind}"
            method = getattr(handler, method_name, None)
            if method:
                results.append(method(event))

    return results


# ---------------------------------------------------------------------------
# Diff / comparison utilities
# ---------------------------------------------------------------------------


def diff_sessions(
    baseline: ReplaySession,
    candidate: ReplaySession,
) -> dict[str, Any]:
    """
    Produce a high-level diff between two sessions.

    Args:
        baseline: The reference session.
        candidate: The session to compare against the baseline.

    Returns:
        A dict with keys: added_kinds, removed_kinds, event_count_delta.
    """
    baseline_kinds = {e.kind for e in baseline.events}
    candidate_kinds = {e.kind for e in candidate.events}
    return {
        "added_kinds": sorted(candidate_kinds - baseline_kinds),
        "removed_kinds": sorted(baseline_kinds - candidate_kinds),
        "event_count_delta": len(candidate.events) - len(baseline.events),
    }


def search_events(
    session: ReplaySession,
    pattern: str,
    *,
    fields: Optional[list[str]] = None,
    case_sensitive: bool = False,
) -> list[ReplayEvent]:
    """
    Search events whose payload fields match a regex pattern.

    Args:
        session: The session to search.
        pattern: Regex pattern to match against string field values.
        fields: Specific payload keys to search; defaults to all string values.
        case_sensitive: Whether the pattern match is case-sensitive.

    Returns:
        List of matching ReplayEvent objects.
    """
    flags = 0 if case_sensitive else re.IGNORECASE
    compiled = re.compile(pattern, flags)
    results = []

    for event in session.events:
        search_fields = (
            {k: event.payload[k] for k in fields if k in event.payload}
            if fields
            else event.payload
        )
        for value in search_fields.values():
            if isinstance(value, str) and compiled.search(value):
                results.append(event)
                break

    return results
