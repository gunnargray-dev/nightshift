"""Session replay module for Awake.

Reconstructs a complete picture of what any previous Awake session did:
files changed, analyses run, PRs opened, refactors applied, health deltas.

Data sources (all optional -- gracefully absent):
- ``.awake/sessions/<session_id>/`` -- per-session JSON artefacts
- ``docs/``                          -- latest analysis outputs
- ``git log``                        -- commit history for the session window

Public API
----------
- ``SessionEvent``     -- a single timestamped event
- ``SessionReplay``    -- full reconstruction for one session
- ``replay_session(session_id, repo_path)`` -> ``SessionReplay``
- ``list_sessions(repo_path)``               -> list of session IDs
- ``save_replay(replay, out_path)``

CLI
---
    awake replay                       # List sessions
    awake replay <session_id>          # Replay a specific session
    awake replay <session_id> --json   # Output raw JSON
    awake replay <session_id> --write  # Write docs/replay_<id>.md
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SessionEvent:
    """A single event that occurred during a session."""

    timestamp: str       # ISO-8601 string or empty
    kind: str            # "analysis" | "pr_opened" | "refactor" | "commit" | "plugin" | "error" | "info"
    summary: str         # One-line description
    detail: Optional[dict] = None  # Optional structured detail

    def to_dict(self) -> dict:
        """Return a serialisable dict."""
        return {
            "timestamp": self.timestamp,
            "kind": self.kind,
            "summary": self.summary,
            "detail": self.detail,
        }

    def to_markdown_row(self) -> str:
        """Render as a Markdown table row."""
        ts = self.timestamp[:19] if self.timestamp else "\u2014"
        return f"| {ts} | `{self.kind}` | {self.summary} |"


@dataclass
class SessionReplay:
    """Full reconstruction of a session."""

    session_id: str
    repo_path: str
    events: list[SessionEvent] = field(default_factory=list)
    health_before: Optional[float] = None
    health_after: Optional[float] = None
    files_changed: list[str] = field(default_factory=list)
    prs_opened: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def health_delta(self) -> Optional[float]:
        """The health score change during the session."""
        if self.health_before is not None and self.health_after is not None:
            return self.health_after - self.health_before
        return None

    def to_dict(self) -> dict:
        """Return a serialisable dict."""
        return {
            "session_id": self.session_id,
            "repo_path": self.repo_path,
            "events": [e.to_dict() for e in self.events],
            "health_before": self.health_before,
            "health_after": self.health_after,
            "health_delta": self.health_delta,
            "files_changed": self.files_changed,
            "prs_opened": self.prs_opened,
            "errors": self.errors,
        }

    def to_markdown(self) -> str:
        """Render the replay as a Markdown report."""
        lines = [
            f"# Session Replay: `{self.session_id}`",
            "",
            "## Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Session ID | `{self.session_id}` |",
            f"| Events | {len(self.events)} |",
            f"| Files changed | {len(self.files_changed)} |",
            f"| PRs opened | {len(self.prs_opened)} |",
        ]
        if self.health_before is not None:
            lines.append(f"| Health before | {self.health_before:.1f} |")
        if self.health_after is not None:
            lines.append(f"| Health after | {self.health_after:.1f} |")
        if self.health_delta is not None:
            sign = "+" if self.health_delta >= 0 else ""
            lines.append(f"| Health delta | {sign}{self.health_delta:.1f} |")
        lines.append("")

        if self.files_changed:
            lines += ["## Files Changed", ""]
            for f in self.files_changed:
                lines.append(f"- `{f}`")
            lines.append("")

        if self.events:
            lines += [
                "## Event Timeline",
                "",
                "| Timestamp | Kind | Summary |",
                "|-----------|------|---------|",
            ]
            for event in self.events:
                lines.append(event.to_markdown_row())
            lines.append("")

        if self.errors:
            lines += ["## Errors", ""]
            for err in self.errors:
                lines.append(f"- {err}")
            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Session directory helpers
# ---------------------------------------------------------------------------


def _session_dir(repo_path: Path, session_id: str) -> Path:
    """Return the path to a session's artefact directory."""
    return repo_path / ".awake" / "sessions" / session_id


def list_sessions(repo_path: str | Path) -> list[str]:
    """Return a sorted list of session IDs found on disk.

    Parameters
    ----------
    repo_path:
        Repository root.

    Returns
    -------
    list[str]
    """
    sessions_dir = Path(repo_path) / ".awake" / "sessions"
    if not sessions_dir.exists():
        return []
    return sorted(p.name for p in sessions_dir.iterdir() if p.is_dir())


def _load_session_json(session_dir: Path, filename: str) -> Optional[dict]:
    """Load a JSON file from the session directory."""
    path = session_dir / filename
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _git_commits_in_window(repo_path: Path, since: str, until: str) -> list[dict]:
    """Return commits between two ISO timestamps."""
    try:
        result = subprocess.run(
            [
                "git", "log",
                f"--after={since}",
                f"--before={until}",
                "--pretty=format:%H|%ai|%s",
            ],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        commits = []
        for line in result.stdout.splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                commits.append({"sha": parts[0], "timestamp": parts[1], "subject": parts[2]})
        return commits
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Replay builder
# ---------------------------------------------------------------------------


def replay_session(
    session_id: str,
    repo_path: str | Path,
) -> SessionReplay:
    """Reconstruct a ``SessionReplay`` for the given *session_id*.

    Parameters
    ----------
    session_id:
        The session UUID or name.
    repo_path:
        Path to the repository root.

    Returns
    -------
    SessionReplay
    """
    repo = Path(repo_path).expanduser().resolve()
    s_dir = _session_dir(repo, session_id)
    replay = SessionReplay(session_id=session_id, repo_path=str(repo))

    if not s_dir.exists():
        replay.errors.append(f"Session directory not found: {s_dir}")
        return replay

    # Load session manifest
    manifest = _load_session_json(s_dir, "manifest.json")
    if manifest:
        replay.health_before = manifest.get("health_before")
        replay.health_after = manifest.get("health_after")
        replay.files_changed = manifest.get("files_changed", [])
        replay.prs_opened = manifest.get("prs_opened", [])

        # Add events from manifest
        for raw_event in manifest.get("events", []):
            replay.events.append(
                SessionEvent(
                    timestamp=raw_event.get("timestamp", ""),
                    kind=raw_event.get("kind", "info"),
                    summary=raw_event.get("summary", ""),
                    detail=raw_event.get("detail"),
                )
            )

    # Load health snapshots
    health_data = _load_session_json(s_dir, "health_report.json")
    if health_data:
        score = health_data.get("overall_score")
        if score is not None:
            replay.events.append(
                SessionEvent(
                    timestamp=health_data.get("generated_at", ""),
                    kind="analysis",
                    summary=f"Health analysis complete: score={score:.1f}",
                    detail={"score": score},
                )
            )

    # Load refactor report
    refactor_data = _load_session_json(s_dir, "refactor_report.json")
    if refactor_data:
        n = refactor_data.get("total_suggestions", 0)
        replay.events.append(
            SessionEvent(
                timestamp="",
                kind="refactor",
                summary=f"Refactor scan: {n} suggestion(s) found",
                detail={"total": n},
            )
        )

    # Load PR data
    pr_data = _load_session_json(s_dir, "pr_score.json")
    if pr_data:
        pr_num = pr_data.get("pr_number")
        score = pr_data.get("score")
        if pr_num:
            replay.prs_opened.append(pr_num)
            replay.events.append(
                SessionEvent(
                    timestamp="",
                    kind="pr_opened",
                    summary=f"PR #{pr_num} scored: {score:.1f}" if score else f"PR #{pr_num} opened",
                    detail=pr_data,
                )
            )

    # Sort events by timestamp
    replay.events.sort(key=lambda e: e.timestamp or "")
    return replay


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def save_replay(replay: SessionReplay, out_path: str | Path) -> None:
    """Save a ``SessionReplay`` as JSON.

    Parameters
    ----------
    replay:
        The replay to save.
    out_path:
        Output file path.
    """
    Path(out_path).write_text(
        json.dumps(replay.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    """CLI entry point for session replay."""
    import argparse

    p = argparse.ArgumentParser(prog="awake-replay")
    p.add_argument("session_id", nargs="?", default=None, help="Session ID to replay")
    p.add_argument("--repo", default=None, help="Repository root")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.add_argument("--write", action="store_true", help="Write markdown to docs/")
    args = p.parse_args(argv)

    if args.repo:
        repo_path = Path(args.repo).expanduser().resolve()
    else:
        repo_path = Path(__file__).resolve().parents[1]

    if not args.session_id:
        # List sessions
        sessions = list_sessions(repo_path)
        if not sessions:
            print("No sessions found.")
        else:
            for s in sessions:
                print(s)
        return 0

    replay = replay_session(args.session_id, repo_path)

    if args.json:
        print(json.dumps(replay.to_dict(), indent=2))
    else:
        md = replay.to_markdown()
        if args.write:
            docs = repo_path / "docs"
            docs.mkdir(exist_ok=True)
            out_path = docs / f"replay_{args.session_id[:8]}.md"
            out_path.write_text(md, encoding="utf-8")
            print(f"  Wrote {out_path}")
        else:
            print(md)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
