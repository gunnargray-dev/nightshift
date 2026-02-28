"""Export system for Nightshift — generate JSON/HTML/Markdown reports.

Provides a unified `ExportEngine` that can collect output from any Nightshift
command and serialize it to multiple formats:

- **Markdown** (.md)  — rendered analysis output
- **JSON** (.json)    — structured machine-readable data
- **HTML** (.html)    — self-contained report with embedded CSS

The exporter can be called standalone or used as a wrapper around any other
module's report object (anything with `.to_markdown()` and `.to_dict()`).

Public API
----------
ExportEngine
export_report(report, out_dir, name, formats) -> dict[str, Path]
render_html_report(title, markdown_content, metadata) -> str
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Protocol for exportable report objects
# ---------------------------------------------------------------------------


@runtime_checkable
class Exportable(Protocol):
    """Any object that has to_markdown() and to_dict()."""

    def to_markdown(self) -> str:
        ...

    def to_dict(self) -> dict:
        ...


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    :root {{
      --bg: #0d1117;
      --surface: #161b22;
      --border: #30363d;
      --text: #c9d1d9;
      --muted: #8b949e;
      --accent: #58a6ff;
      --green: #3fb950;
      --yellow: #d29922;
      --orange: #f0883e;
      --red: #f85149;
      --link: #58a6ff;
      --code-bg: #1f2428;
      --th-bg: #21262d;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      font-size: 14px;
      line-height: 1.6;
      padding: 2rem;
    }}
    .container {{ max-width: 960px; margin: 0 auto; }}
    .header {{
      border-bottom: 1px solid var(--border);
      padding-bottom: 1.5rem;
      margin-bottom: 2rem;
    }}
    .header h1 {{
      font-size: 1.8rem;
      color: var(--text);
      margin-bottom: 0.4rem;
    }}
    .meta {{ color: var(--muted); font-size: 0.85rem; }}
    .meta span {{ margin-right: 1rem; }}
    h1, h2, h3, h4 {{
      color: var(--text);
      margin-top: 1.5rem;
      margin-bottom: 0.6rem;
      border-bottom: 1px solid var(--border);
      padding-bottom: 0.3rem;
    }}
    h1 {{ font-size: 1.5rem; border-bottom: 2px solid var(--border); }}
    h2 {{ font-size: 1.2rem; }}
    h3 {{ font-size: 1rem; border-bottom: none; color: var(--accent); }}
    p {{ margin: 0.6rem 0; }}
    a {{ color: var(--link); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    code {{
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
      font-size: 0.85em;
      background: var(--code-bg);
      padding: 0.1em 0.3em;
      border-radius: 3px;
      border: 1px solid var(--border);
    }}
    pre {{
      background: var(--code-bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 1rem;
      overflow-x: auto;
      margin: 0.8rem 0;
    }}
    pre code {{
      background: none;
      border: none;
      padding: 0;
      font-size: 0.82em;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 1rem 0;
      font-size: 0.88rem;
    }}
    th {{
      background: var(--th-bg);
      color: var(--text);
      font-weight: 600;
      text-align: left;
      padding: 0.5rem 0.75rem;
      border: 1px solid var(--border);
    }}
    td {{
      padding: 0.4rem 0.75rem;
      border: 1px solid var(--border);
    }}
    tr:nth-child(even) td {{ background: rgba(255,255,255,0.03); }}
    blockquote {{
      border-left: 3px solid var(--accent);
      padding: 0.4rem 0.8rem;
      margin: 0.8rem 0;
      color: var(--muted);
      background: rgba(88,166,255,0.05);
      border-radius: 0 4px 4px 0;
    }}
    hr {{
      border: none;
      border-top: 1px solid var(--border);
      margin: 1.5rem 0;
    }}
    ul, ol {{ padding-left: 1.5rem; margin: 0.5rem 0; }}
    li {{ margin: 0.2rem 0; }}
    strong {{ color: var(--text); font-weight: 600; }}
    em {{ color: var(--muted); }}
    .badge {{
      display: inline-block;
      padding: 0.15rem 0.45rem;
      border-radius: 12px;
      font-size: 0.75rem;
      font-weight: 600;
    }}
    .badge-green {{ background: rgba(63,185,80,0.15); color: var(--green); }}
    .badge-yellow {{ background: rgba(210,153,34,0.15); color: var(--yellow); }}
    .badge-red {{ background: rgba(248,81,73,0.15); color: var(--red); }}
    .footer {{
      margin-top: 3rem;
      padding-top: 1rem;
      border-top: 1px solid var(--border);
      color: var(--muted);
      font-size: 0.8rem;
      text-align: center;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>🌙 {title}</h1>
      <div class="meta">
        {meta_items}
      </div>
    </div>
    <div class="content">
{html_body}
    </div>
    <div class="footer">
      Generated by <strong>Nightshift</strong> · {generated_at}
    </div>
  </div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Markdown → HTML converter (minimal, no dependencies)
# ---------------------------------------------------------------------------


def _md_to_html(md: str) -> str:
    """Convert Markdown to HTML (minimal subset used by Nightshift reports)."""
    html_lines: list[str] = []
    lines = md.split("\n")
    i = 0
    in_code_block = False
    in_table = False
    in_list = False
    in_blockquote = False

    def _inline(text: str) -> str:
        """Process inline Markdown elements."""
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
        text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", text)
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
        return text

    while i < len(lines):
        line = lines[i]

        if line.strip().startswith("```"):
            if not in_code_block:
                in_code_block = True
                html_lines.append(f"<pre><code>")
            else:
                in_code_block = False
                html_lines.append("</code></pre>")
            i += 1
            continue

        if in_code_block:
            line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            html_lines.append(line)
            i += 1
            continue

        if in_table and not line.startswith("|"):
            html_lines.append("</tbody></table>")
            in_table = False
        if in_list and not line.strip().startswith(("-", "*", "+")):
            html_lines.append("</ul>")
            in_list = False
        if in_blockquote and not line.strip().startswith(">"):
            html_lines.append("</blockquote>")
            in_blockquote = False

        if line.startswith("######"):
            html_lines.append(f"<h6>{_inline(line[6:].strip())}</h6>")
        elif line.startswith("#####"):
            html_lines.append(f"<h5>{_inline(line[5:].strip())}</h5>")
        elif line.startswith("####"):
            html_lines.append(f"<h4>{_inline(line[4:].strip())}</h4>")
        elif line.startswith("###"):
            html_lines.append(f"<h3>{_inline(line[3:].strip())}</h3>")
        elif line.startswith("##"):
            html_lines.append(f"<h2>{_inline(line[2:].strip())}</h2>")
        elif line.startswith("#"):
            html_lines.append(f"<h1>{_inline(line[1:].strip())}</h1>")
        elif line.strip() in ("---", "***", "___"):
            html_lines.append("<hr>")
        elif line.strip().startswith(">"):
            if not in_blockquote:
                html_lines.append("<blockquote>")
                in_blockquote = True
            html_lines.append(f"<p>{_inline(line.strip().lstrip('>').strip())}</p>")
        elif line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.match(r":?-+:?", c) for c in cells if c):
                i += 1
                continue
            if not in_table:
                html_lines.append('<table><thead><tr>')
                for c in cells:
                    html_lines.append(f"<th>{_inline(c)}</th>")
                html_lines.append("</tr></thead><tbody>")
                in_table = True
            else:
                html_lines.append("<tr>")
                for c in cells:
                    html_lines.append(f"<td>{_inline(c)}</td>")
                html_lines.append("</tr>")
        elif line.strip().startswith(("- ", "* ", "+ ")):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{_inline(line.strip()[2:])}</li>")
        elif re.match(r"^\d+\.\s", line.strip()):
            html_lines.append(f"<li>{_inline(re.sub(r'^\d+\.\s*', '', line.strip()))}</li>")
        elif not line.strip():
            html_lines.append("")
        else:
            html_lines.append(f"<p>{_inline(line)}</p>")

        i += 1

    if in_code_block:
        html_lines.append("</code></pre>")
    if in_table:
        html_lines.append("</tbody></table>")
    if in_list:
        html_lines.append("</ul>")
    if in_blockquote:
        html_lines.append("</blockquote>")

    return "\n".join(html_lines)


# ---------------------------------------------------------------------------
# HTML renderer
# ---------------------------------------------------------------------------


def render_html_report(
    title: str,
    markdown_content: str,
    metadata: Optional[dict[str, str]] = None,
) -> str:
    """Render a full HTML page from Markdown content."""
    meta_items_html = ""
    if metadata:
        parts = [f"<span><strong>{k}:</strong> {v}</span>" for k, v in metadata.items()]
        meta_items_html = "\n        ".join(parts)

    html_body = _md_to_html(markdown_content)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return _HTML_TEMPLATE.format(
        title=title,
        meta_items=meta_items_html,
        html_body=html_body,
        generated_at=generated_at,
    )


# ---------------------------------------------------------------------------
# Export engine
# ---------------------------------------------------------------------------


FORMATS = ("json", "markdown", "html")


@dataclass
class ExportResult:
    """Result of an export operation."""

    name: str
    files: dict[str, Path] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "files": {k: str(v) for k, v in self.files.items()},
            "errors": self.errors,
        }


class ExportEngine:
    """Wraps any Nightshift report object and exports it to multiple formats."""

    def __init__(
        self,
        name: str,
        out_dir: Path,
        title: Optional[str] = None,
    ) -> None:
        self.name = name
        self.out_dir = out_dir
        self.title = title or name.replace("-", " ").replace("_", " ").title()

    def export(
        self,
        report: Any,
        formats: Optional[list[str]] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> ExportResult:
        """Export *report* to the requested formats."""
        if formats is None:
            formats = list(FORMATS)

        self.out_dir.mkdir(parents=True, exist_ok=True)
        result = ExportResult(name=self.name)

        for fmt in formats:
            try:
                path = self._export_one(report, fmt, metadata or {})
                result.files[fmt] = path
            except Exception as exc:
                result.errors.append(f"{fmt}: {exc}")

        return result

    def _export_one(
        self,
        report: Any,
        fmt: str,
        metadata: dict[str, str],
    ) -> Path:
        fmt = fmt.lower()
        if fmt == "json":
            path = self.out_dir / f"{self.name}.json"
            if hasattr(report, "to_json"):
                path.write_text(report.to_json(), encoding="utf-8")
            elif hasattr(report, "to_dict"):
                path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
            else:
                path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        elif fmt in ("markdown", "md"):
            path = self.out_dir / f"{self.name}.md"
            if hasattr(report, "to_markdown"):
                path.write_text(report.to_markdown(), encoding="utf-8")
            else:
                path.write_text(str(report), encoding="utf-8")
        elif fmt == "html":
            path = self.out_dir / f"{self.name}.html"
            if hasattr(report, "to_markdown"):
                md = report.to_markdown()
            else:
                md = str(report)
            html = render_html_report(self.title, md, metadata)
            path.write_text(html, encoding="utf-8")
        else:
            raise ValueError(f"Unknown format: {fmt!r}. Choose from: {FORMATS}")

        return path


def export_report(
    report: Any,
    out_dir: Path,
    name: str,
    formats: Optional[list[str]] = None,
    title: Optional[str] = None,
    metadata: Optional[dict[str, str]] = None,
) -> ExportResult:
    """Convenience function to export a report without creating an ExportEngine manually."""
    engine = ExportEngine(name=name, out_dir=out_dir, title=title)
    return engine.export(report, formats=formats, metadata=metadata)
