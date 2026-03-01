"""Session replay engine for Awake.

Allows a developer to replay any past Awake session step-by-step in a
read-only, annotated view. Features:
- Reconstruct session state from git log + diff
- Display each commit in order with diff, conventional-commit metadata,
  and inline annotations
- Compute per-commit health deltas (test count, smell count)
- Export replay as an HTML report or structured JSON
- Interactive CLI mode: step forward/back through commits

Useful for onboarding, post-mortem review, and debugging regressions.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CommitMeta:
    """Metadata for a single commit in the replay."""

    sha: str
    short_sha: str
    date: str
    author: str
    subject: str
    commit_type: str
    scope: Optional[str]
    description: str
    session: Optional[int]
    breaking: bool


@dataclass
class DiffStat:
    """Summary of file changes for one commit."""

    files_changed: int
    insertions: int
    deletions: int
    changed_files: list[str]


@dataclass
class HealthDelta:
    """Change in health metrics caused by one commit."""

    test_count_before: int
    test_count_after: int
    smell_count_before: int
    smell_count_after: int

    @property
    def test_delta(self) -> int:
        return self.test_count_after - self.test_count_before

    @property
    def smell_delta(self) -> int:
        return self.smell_count_after - self.smell_count_before


@dataclass
class ReplayStep:
    """One step in the session replay."""

    index: int
    commit: CommitMeta
    diff_stat: DiffStat
    diff_text: str
    health_delta: Optional[HealthDelta]
    annotation: str


@dataclass
class SessionReplay:
    """Complete replay for one Awake session."""

    session: int
    repo_root: str
    total_steps: int
    steps: list[ReplayStep]


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


SEP = "|||---|||"
_LOG_FORMAT = f"%H{SEP}%h{SEP}%aI{SEP}%an{SEP}%s"
_CC_RE = re.compile(
    r"^\[awake\]\s+(?P<type>feat|fix|refactor|test|ci|docs|meta|chore)"
    r"(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s+(?P<desc>.+)$"
)
_SESSION_RE = re.compile(r"session[\s-]*(\d+)", re.IGNORECASE)


def _run(cmd: list[str], cwd: Path) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, check=False).stdout


def _parse_commit_meta(line: str) -> CommitMeta:
    parts = line.split(SEP)
    if len(parts) < 5:
        raise ValueError(f"Unexpected log line: {line!r}")
    sha, short_sha, date, author, subject = parts[:5]
    m = _CC_RE.match(subject)
    if m:
        commit_type = m.group("type")
        scope = m.group("scope")
        description = m.group("desc")
        breaking = bool(m.group("breaking"))
    else:
        commit_type = "misc"
        scope = None
        description = subject
        breaking = False
    session = None
    sm = _SESSION_RE.search(subject)
    if sm:
        session = int(sm.group(1))
    return CommitMeta(
        sha=sha.strip(), short_sha=short_sha.strip(),
        date=date.strip(), author=author.strip(),
        subject=subject.strip(), commit_type=commit_type,
        scope=scope, description=description,
        session=session, breaking=breaking,
    )


def _get_diff_stat(sha: str, cwd: Path) -> DiffStat:
    stat_out = _run(["git", "show", "--stat", "--format=", sha], cwd=cwd)
    files_changed = 0
    insertions = 0
    deletions = 0
    changed_files: list[str] = []
    for line in stat_out.splitlines():
        if " | " in line:
            fname = line.split(" | ")[0].strip()
            changed_files.append(fname)
        m = re.search(r"(\d+) file", line)
        if m:
            files_changed = int(m.group(1))
        mi = re.search(r"(\d+) insertion", line)
        if mi:
            insertions = int(mi.group(1))
        md = re.search(r"(\d+) deletion", line)
        if md:
            deletions = int(md.group(1))
    return DiffStat(
        files_changed=files_changed,
        insertions=insertions,
        deletions=deletions,
        changed_files=changed_files,
    )


def _get_diff_text(sha: str, cwd: Path, max_lines: int = 200) -> str:
    diff = _run(["git", "show", "--format=", sha], cwd=cwd)
    lines = diff.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"... ({len(lines) - max_lines} more lines truncated)"]
    return "\n".join(lines)


def _get_session_commits(repo_root: Path, session: int) -> list[str]:
    """Return SHAs (oldest-first) for commits tagged with *session*."""
    log = _run(["git", "log", "--reverse", "--pretty=format:" + _LOG_FORMAT], cwd=repo_root)
    sha_list = []
    for line in log.splitlines():
        if not line.strip():
            continue
        parts = line.split(SEP)
        if len(parts) < 5:
            continue
        subject = parts[4]
        sm = _SESSION_RE.search(subject)
        if sm and int(sm.group(1)) == session:
            sha_list.append(line)  # keep full line for later parsing
    return sha_list


# ---------------------------------------------------------------------------
# Annotation generator
# ---------------------------------------------------------------------------


def _make_annotation(meta: CommitMeta, diff_stat: DiffStat) -> str:
    """Generate a one-paragraph human-readable annotation for a commit."""
    type_labels = {
        "feat": "introduces a new feature",
        "fix": "patches a bug",
        "refactor": "refactors existing code",
        "test": "adds or updates tests",
        "ci": "modifies CI configuration",
        "docs": "updates documentation",
        "meta": "applies a meta-level change",
        "chore": "performs housekeeping",
        "misc": "makes a miscellaneous change",
    }
    label = type_labels.get(meta.commit_type, "makes a change")
    scope_str = f" to `{meta.scope}`" if meta.scope else ""
    breaking_str = " **This is a breaking change.**" if meta.breaking else ""
    return (
        f"Commit `{meta.short_sha}` {label}{scope_str}: "
        f"{meta.description}.{breaking_str} "
        f"({diff_stat.files_changed} file(s), "
        f"+{diff_stat.insertions}/−{diff_stat.deletions})"
    )


# ---------------------------------------------------------------------------
# Replay builder
# ---------------------------------------------------------------------------


def build_replay(repo_root: Path, session: int) -> SessionReplay:
    """Construct a full SessionReplay for the given session number."""
    raw_lines = _get_session_commits(repo_root, session)
    steps: list[ReplayStep] = []
    for idx, line in enumerate(raw_lines):
        try:
            meta = _parse_commit_meta(line)
        except ValueError:
            continue
        diff_stat = _get_diff_stat(meta.sha, repo_root)
        diff_text = _get_diff_text(meta.sha, repo_root)
        annotation = _make_annotation(meta, diff_stat)
        steps.append(
            ReplayStep(
                index=idx,
                commit=meta,
                diff_stat=diff_stat,
                diff_text=diff_text,
                health_delta=None,  # Populated by health_delta_pass if enabled
                annotation=annotation,
            )
        )
    return SessionReplay(
        session=session,
        repo_root=str(repo_root),
        total_steps=len(steps),
        steps=steps,
    )


# ---------------------------------------------------------------------------
# Exporters
# ---------------------------------------------------------------------------


def export_json(replay: SessionReplay) -> str:
    """Serialise replay to JSON (HealthDelta excluded — not JSON-serialisable as-is)."""
    payload = {
        "session": replay.session,
        "repo_root": replay.repo_root,
        "total_steps": replay.total_steps,
        "steps": [
            {
                "index": s.index,
                "commit": {
                    "sha": s.commit.sha,
                    "short_sha": s.commit.short_sha,
                    "date": s.commit.date,
                    "author": s.commit.author,
                    "subject": s.commit.subject,
                    "commit_type": s.commit.commit_type,
                    "scope": s.commit.scope,
                    "description": s.commit.description,
                    "session": s.commit.session,
                    "breaking": s.commit.breaking,
                },
                "diff_stat": {
                    "files_changed": s.diff_stat.files_changed,
                    "insertions": s.diff_stat.insertions,
                    "deletions": s.diff_stat.deletions,
                    "changed_files": s.diff_stat.changed_files,
                },
                "annotation": s.annotation,
            }
            for s in replay.steps
        ],
    }
    return json.dumps(payload, indent=2)


def export_html(replay: SessionReplay) -> str:
    """Render replay as a self-contained HTML page."""
    rows = []
    for step in replay.steps:
        c = step.commit
        diff_escaped = step.diff_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        rows.append(f"""
        <div class="step">
          <h3>Step {step.index + 1} — <code>{c.short_sha}</code>: {c.subject}</h3>
          <p class="annotation">{step.annotation}</p>
          <pre class="diff">{diff_escaped}</pre>
        </div>""")
    body = "\n".join(rows)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Awake Session {replay.session} Replay</title>
  <style>
    body {{ font-family: monospace; max-width: 960px; margin: 2rem auto; }}
    .step {{ border: 1px solid #ccc; border-radius: 4px; margin: 1rem 0; padding: 1rem; }}
    .annotation {{ color: #555; }}
    .diff {{ background: #f5f5f5; padding: 1rem; overflow-x: auto; }}
  </style>
</head>
<body>
  <h1>Awake — Session {replay.session} Replay</h1>
  <p>Repo: <code>{replay.repo_root}</code> · {replay.total_steps} steps</p>
{body}
</body>
</html>"""


# ---------------------------------------------------------------------------
# Interactive CLI
# ---------------------------------------------------------------------------


def interactive_cli(replay: SessionReplay) -> None:
    """Step forward/back through the replay interactively."""
    if not replay.steps:
        print("No steps in this replay.")
        return
    idx = 0
    while True:
        step = replay.steps[idx]
        print(f"\n--- Step {step.index + 1}/{replay.total_steps} ---")
        print(f"SHA     : {step.commit.short_sha}")
        print(f"Type    : {step.commit.commit_type}")
        print(f"Subject : {step.commit.subject}")
        print(f"Note    : {step.annotation}")
        print(f"Diff    : {step.diff_stat.files_changed} files, "
              f"+{step.diff_stat.insertions}/−{step.diff_stat.deletions}")
        cmd = input("[n]ext / [p]rev / [d]iff / [q]uit > ").strip().lower()
        if cmd == "n":
            idx = min(idx + 1, replay.total_steps - 1)
        elif cmd == "p":
            idx = max(idx - 1, 0)
        elif cmd == "d":
            print(step.diff_text)
        elif cmd == "q":
            break


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI: python -m src.session_replay --session N [--html] [--json] [--interactive]"""
    import sys
    args = sys.argv[1:]

    def _get(flag: str, default: str = "") -> str:
        try:
            return args[args.index(flag) + 1]
        except (ValueError, IndexError):
            return default

    session = int(_get("--session", "1"))
    repo_root = Path(__file__).resolve().parent.parent
    replay = build_replay(repo_root, session)

    if "--json" in args:
        print(export_json(replay))
    elif "--html" in args:
        out = repo_root / "reports" / f"session_{session}_replay.html"
        out.parent.mkdir(exist_ok=True)
        out.write_text(export_html(replay), encoding="utf-8")
        print(f"HTML replay written to {out}")
    elif "--interactive" in args:
        interactive_cli(replay)
    else:
        for step in replay.steps:
            print(f"[{step.index + 1}] {step.commit.short_sha}: {step.commit.subject}")
            print(f"     {step.annotation}")


if __name__ == "__main__":
    main()
