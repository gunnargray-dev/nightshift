"""Session replay module for Awake.

Reconstructs a full developer "session" -- a time-ordered sequence of file
edits, test runs, and CLI invocations -- from Git history and (optionally)
shell history files.  The replayed session can be:

- Printed as a human-readable timeline
- Exported as JSON for downstream analysis
- Fed into ``trend_data.py`` for charting

Data sources
------------
``git log --stat``
    File-level change events with timestamps and commit messages.

``~/.bash_history`` / ``~/.zsh_history``
    Shell commands (best-effort; not always available or reliable).

Public API
----------
- ``SessionEvent``     -- a single event in the replay
- ``Session``          -- ordered list of events
- ``build_session(repo_path, *, since, until)`` -> ``Session``
- ``save_session(session, out_path)``

CLI
---
    awake replay [--since DATE] [--until DATE] [--json] [--output PATH]
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class SessionEvent:
    """A single event in a developer session."""

    timestamp: str  # ISO-8601
    kind: str  # "commit" | "shell"
    summary: str
    files_changed: list[str] = field(default_factory=list)
    author: str = ""
    sha: str = ""
    raw: str = ""


@dataclass
class Session:
    """An ordered collection of session events."""

    events: list[SessionEvent] = field(default_factory=list)
    repo: str = ""
    since: str = ""
    until: str = ""

    def add(self, event: SessionEvent) -> None:
        """Append *event* to the session and keep events sorted by timestamp."""
        self.events.append(event)
        self.events.sort(key=lambda e: e.timestamp)


# ---------------------------------------------------------------------------
# Git log parser
# ---------------------------------------------------------------------------

_COMMIT_SEP = "AWAKE_COMMIT_SEP"
_GIT_FORMAT = f"--pretty=format:{_COMMIT_SEP}%H|%ae|%ai|%s"


def _run_git(args: list[str], cwd: str) -> str:
    """Run a git command and return stdout, or empty string on failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def _parse_git_log(raw: str) -> list[SessionEvent]:
    """Parse the output of ``git log --stat`` into :class:`SessionEvent` objects."""
    events: list[SessionEvent] = []
    blocks = raw.split(_COMMIT_SEP)
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        if not lines:
            continue
        header = lines[0]
        parts = header.split("|", 3)
        if len(parts) < 4:
            continue
        sha, author, ts_raw, summary = parts
        # Parse timestamp
        try:
            dt = datetime.fromisoformat(ts_raw.strip())
            ts = dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            ts = ts_raw.strip()

        # Collect changed files from --stat output
        files: list[str] = []
        for line in lines[1:]:
            # Stat lines look like: " src/health.py | 42 ++++--"
            m = re.match(r"^\s+(.+?)\s+\|", line)
            if m:
                files.append(m.group(1).strip())

        events.append(
            SessionEvent(
                timestamp=ts,
                kind="commit",
                summary=summary.strip(),
                files_changed=files,
                author=author.strip(),
                sha=sha.strip(),
                raw=block,
            )
        )
    return events


# ---------------------------------------------------------------------------
# Shell history parser
# ---------------------------------------------------------------------------


def _parse_bash_history(path: Path) -> list[SessionEvent]:
    """Parse a ``~/.bash_history`` file into events (no timestamps)."""
    events: list[SessionEvent] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return events
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        events.append(
            SessionEvent(
                timestamp="",
                kind="shell",
                summary=line[:120],
                raw=line,
            )
        )
    return events


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_session(
    repo_path: str | Path,
    *,
    since: str = "",
    until: str = "",
    include_shell: bool = False,
) -> Session:
    """Reconstruct a developer session from git history.

    Parameters
    ----------
    repo_path:
        Path to the git repository.
    since:
        Only include commits after this date (ISO-8601 or git date format).
    until:
        Only include commits before this date.
    include_shell:
        If *True*, attempt to merge shell history events.

    Returns
    -------
    Session
        The reconstructed session.
    """
    root = Path(repo_path)
    session = Session(repo=str(root), since=since, until=until)

    git_args = ["log", "--stat", _GIT_FORMAT]
    if since:
        git_args += [f"--after={since}"]
    if until:
        git_args += [f"--before={until}"]

    raw_log = _run_git(git_args, cwd=str(root))
    for event in _parse_git_log(raw_log):
        session.add(event)

    if include_shell:
        history_files = [
            Path.home() / ".bash_history",
            Path.home() / ".zsh_history",
        ]
        for hf in history_files:
            if hf.exists():
                for ev in _parse_bash_history(hf):
                    session.add(ev)

    return session


# ---------------------------------------------------------------------------
# Serialiser
# ---------------------------------------------------------------------------


def save_session(session: Session, out_path: str | Path) -> None:
    """Serialise *session* to JSON at *out_path*.

    Parameters
    ----------
    session:
        The session to serialise.
    out_path:
        Destination file path.
    """
    data = {
        "repo": session.repo,
        "since": session.since,
        "until": session.until,
        "event_count": len(session.events),
        "events": [
            {
                "timestamp": e.timestamp,
                "kind": e.kind,
                "summary": e.summary,
                "files_changed": e.files_changed,
                "author": e.author,
                "sha": e.sha,
            }
            for e in session.events
        ],
    }
    Path(out_path).write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the session replay module.

    Parameters
    ----------
    argv:
        Command-line arguments.

    Returns
    -------
    int
        Exit code.
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="awake replay",
        description="Reconstruct a developer session from git history.",
    )
    parser.add_argument("repo", nargs="?", default=".", help="Repo root")
    parser.add_argument("--since", default="", help="Include commits after DATE")
    parser.add_argument("--until", default="", help="Include commits before DATE")
    parser.add_argument("--json", action="store_true", help="Emit JSON to stdout")
    parser.add_argument("--shell", action="store_true", help="Include shell history")
    parser.add_argument("--output", "-o", default="", help="Write to file")
    args = parser.parse_args(argv)

    root = Path(args.repo).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        return 1

    session = build_session(
        root, since=args.since, until=args.until, include_shell=args.shell
    )

    if args.json or args.output:
        data = {
            "repo": session.repo,
            "since": session.since,
            "until": session.until,
            "event_count": len(session.events),
            "events": [
                {
                    "timestamp": e.timestamp,
                    "kind": e.kind,
                    "summary": e.summary,
                    "files_changed": e.files_changed,
                    "author": e.author,
                    "sha": e.sha,
                }
                for e in session.events
            ],
        }
        json_str = json.dumps(data, indent=2)
        if args.output:
            Path(args.output).write_text(json_str, encoding="utf-8")
            print(f"Session written to {args.output}")
        else:
            print(json_str)
    else:
        print(f"Session for {session.repo}")
        if session.since or session.until:
            print(f"  Range: {session.since or '*'} .. {session.until or '*'}")
        print(f"  Events: {len(session.events)}")
        for ev in session.events:
            ts = ev.timestamp[:19] if ev.timestamp else "(no time)"
            print(f"  {ts}  [{ev.kind:6s}]  {ev.summary[:80]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
