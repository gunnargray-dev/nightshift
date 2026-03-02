"""Diff visualization utilities."""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class DiffChunk:
    """A contiguous block of diff lines."""

    tag: str  # equal | replace | insert | delete
    old_start: int
    old_lines: list[str]
    new_start: int
    new_lines: list[str]


@dataclass
class FileDiff:
    """Structured diff between two versions of a file."""

    path: str
    old_path: Optional[str]
    chunks: list[DiffChunk] = field(default_factory=list)

    @property
    def added(self) -> int:
        return sum(len(c.new_lines) for c in self.chunks if c.tag in ("insert", "replace"))

    @property
    def removed(self) -> int:
        return sum(len(c.old_lines) for c in self.chunks if c.tag in ("delete", "replace"))

    @property
    def is_rename(self) -> bool:
        return self.old_path is not None and self.old_path != self.path


def _parse_unified_diff(raw: str) -> list[FileDiff]:
    """Parse a unified diff string into :class:`FileDiff` objects."""
    diffs: list[FileDiff] = []
    current: Optional[FileDiff] = None
    current_chunk: Optional[DiffChunk] = None
    old_lineno = 0
    new_lineno = 0

    for line in raw.splitlines():
        if line.startswith("--- "):
            old_path = line[4:].split("\t")[0].strip()
            if old_path.startswith("a/"):
                old_path = old_path[2:]
        elif line.startswith("+++ "):
            new_path = line[4:].split("\t")[0].strip()
            if new_path.startswith("b/"):
                new_path = new_path[2:]
            current = FileDiff(path=new_path, old_path=old_path)  # type: ignore[possibly-undefined]
            diffs.append(current)
            current_chunk = None
        elif line.startswith("@@"):
            # Parse @@ -old_start,old_count +new_start,new_count @@
            parts = line.split(" ")
            old_info = parts[1][1:]  # strip '-'
            new_info = parts[2][1:]  # strip '+'
            old_start = int(old_info.split(",")[0])
            new_start = int(new_info.split(",")[0])
            old_lineno = old_start
            new_lineno = new_start
            current_chunk = DiffChunk(
                tag="equal", old_start=old_start, old_lines=[], new_start=new_start, new_lines=[]
            )
            if current:
                current.chunks.append(current_chunk)
        elif current_chunk is not None:
            if line.startswith("-"):
                if current_chunk.tag not in ("delete", "replace"):
                    current_chunk = DiffChunk(
                        tag="delete",
                        old_start=old_lineno,
                        old_lines=[],
                        new_start=new_lineno,
                        new_lines=[],
                    )
                    if current:
                        current.chunks.append(current_chunk)
                current_chunk.old_lines.append(line[1:])
                old_lineno += 1
            elif line.startswith("+"):
                if current_chunk.tag == "delete":
                    current_chunk.tag = "replace"
                elif current_chunk.tag not in ("insert", "replace"):
                    current_chunk = DiffChunk(
                        tag="insert",
                        old_start=old_lineno,
                        old_lines=[],
                        new_start=new_lineno,
                        new_lines=[],
                    )
                    if current:
                        current.chunks.append(current_chunk)
                current_chunk.new_lines.append(line[1:])
                new_lineno += 1
            else:
                # context line
                if current_chunk.tag != "equal":
                    current_chunk = DiffChunk(
                        tag="equal",
                        old_start=old_lineno,
                        old_lines=[],
                        new_start=new_lineno,
                        new_lines=[],
                    )
                    if current:
                        current.chunks.append(current_chunk)
                ctx = line[1:] if line.startswith(" ") else line
                current_chunk.old_lines.append(ctx)
                current_chunk.new_lines.append(ctx)
                old_lineno += 1
                new_lineno += 1

    return diffs


def compute_diff(old_text: str, new_text: str, path: str = "file") -> FileDiff:
    """Compute a structured diff between two strings."""
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    chunks: list[DiffChunk] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        chunks.append(
            DiffChunk(
                tag=tag,
                old_start=i1,
                old_lines=old_lines[i1:i2],
                new_start=j1,
                new_lines=new_lines[j1:j2],
            )
        )
    return FileDiff(path=path, old_path=None, chunks=chunks)


def render_html(diff: FileDiff, context_lines: int = 3) -> str:
    """Render a :class:`FileDiff` as an HTML side-by-side view."""
    rows: list[str] = []
    for chunk in diff.chunks:
        if chunk.tag == "equal":
            # Show only context_lines lines of context
            lines = chunk.old_lines[-context_lines:] if context_lines else chunk.old_lines
            for line in lines:
                escaped = line.rstrip("\n").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                rows.append(
                    f'<tr class="ctx"><td class="ln"></td><td>{escaped}</td>'
                    f'<td class="ln"></td><td>{escaped}</td></tr>'
                )
        elif chunk.tag in ("delete", "replace"):
            for i, line in enumerate(chunk.old_lines):
                escaped_old = line.rstrip("\n").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                if chunk.tag == "replace" and i < len(chunk.new_lines):
                    escaped_new = chunk.new_lines[i].rstrip("\n").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    rows.append(
                        f'<tr class="chg"><td class="ln del">{chunk.old_start + i + 1}</td>'
                        f'<td class="del">{escaped_old}</td>'
                        f'<td class="ln add">{chunk.new_start + i + 1}</td>'
                        f'<td class="add">{escaped_new}</td></tr>'
                    )
                else:
                    rows.append(
                        f'<tr class="del"><td class="ln del">{chunk.old_start + i + 1}</td>'
                        f'<td class="del">{escaped_old}</td><td></td><td></td></tr>'
                    )
        elif chunk.tag == "insert":
            for i, line in enumerate(chunk.new_lines):
                escaped = line.rstrip("\n").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                rows.append(
                    f'<tr class="add"><td></td><td></td>'
                    f'<td class="ln add">{chunk.new_start + i + 1}</td>'
                    f'<td class="add">{escaped}</td></tr>'
                )

    style = (
        "<style>"
        "table{border-collapse:collapse;font-family:monospace;font-size:13px;width:100%}"
        "td{padding:2px 6px;white-space:pre}"
        ".del{background:#ffeef0}.add{background:#e6ffed}"
        ".ln{color:#999;user-select:none;min-width:40px;text-align:right}"
        "</style>"
    )
    table = "<table>" + "".join(rows) + "</table>"
    return f"<div class='diff-view'>{style}{table}</div>"


def render_terminal(diff: FileDiff, color: bool = True) -> str:
    """Render a diff as a colored terminal string."""
    RED = "\033[31m" if color else ""
    GREEN = "\033[32m" if color else ""
    RESET = "\033[0m" if color else ""
    lines: list[str] = [f"--- {diff.old_path or diff.path}", f"+++ {diff.path}"]
    for chunk in diff.chunks:
        if chunk.tag == "equal":
            for line in chunk.old_lines[-3:]:
                lines.append(" " + line.rstrip("\n"))
        elif chunk.tag in ("delete", "replace"):
            for line in chunk.old_lines:
                lines.append(f"{RED}-{line.rstrip(chr(10))}{RESET}")
            if chunk.tag == "replace":
                for line in chunk.new_lines:
                    lines.append(f"{GREEN}+{line.rstrip(chr(10))}{RESET}")
        elif chunk.tag == "insert":
            for line in chunk.new_lines:
                lines.append(f"{GREEN}+{line.rstrip(chr(10))}{RESET}")
    return "\n".join(lines)


def diff_files(old_path: Path, new_path: Path) -> FileDiff:
    """Diff two files on disk."""
    old_text = old_path.read_text(encoding="utf-8", errors="replace")
    new_text = new_path.read_text(encoding="utf-8", errors="replace")
    return compute_diff(old_text, new_text, path=str(new_path))
