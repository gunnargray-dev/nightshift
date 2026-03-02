"""AI-powered release notes generator."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .changelog import ChangelogEntry, ChangelogRelease, get_commits_between


@dataclass
class ReleaseNotesConfig:
    """Configuration for release notes generation."""

    model: str = "gpt-4o-mini"
    audience: str = "technical"  # technical | non-technical | marketing
    max_bullets: int = 20
    include_breaking: bool = True
    include_fixes: bool = True
    tone: str = "professional"  # professional | casual | exciting


# ---------------------------------------------------------------------------
# Templates per audience
# ---------------------------------------------------------------------------

_INTRO_TEMPLATES: dict[str, str] = {
    "technical": "This release includes the following changes:",
    "non-technical": "Here's what's new in this version:",
    "marketing": "We're excited to announce the following improvements:",
}

_SECTION_HEADERS: dict[str, dict[str, str]] = {
    "technical": {
        "breaking": "Breaking Changes",
        "features": "New Features",
        "fixes": "Bug Fixes",
        "other": "Other Changes",
    },
    "non-technical": {
        "breaking": "Important Changes",
        "features": "What's New",
        "fixes": "Improvements",
        "other": "Under the Hood",
    },
    "marketing": {
        "breaking": "Important Updates",
        "features": "Exciting New Features",
        "fixes": "Quality Improvements",
        "other": "Additional Updates",
    },
}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _entry_to_bullet(entry: ChangelogEntry, audience: str) -> str:
    """Convert a changelog entry to a release-note bullet."""
    desc = entry.description
    if audience == "non-technical":
        # Soften technical language
        desc = desc.replace("refactor", "improve").replace("deprecate", "phase out")
    scope_prefix = f"[{entry.scope}] " if entry.scope else ""
    return f"- {scope_prefix}{desc}"


def _render_release_notes(
    release: ChangelogRelease,
    config: ReleaseNotesConfig,
) -> str:
    audience = config.audience
    headers = _SECTION_HEADERS.get(audience, _SECTION_HEADERS["technical"])
    intro = _INTRO_TEMPLATES.get(audience, _INTRO_TEMPLATES["technical"])

    sections: dict[str, list[str]] = {
        "breaking": [],
        "features": [],
        "fixes": [],
        "other": [],
    }

    for entry in release.entries[: config.max_bullets]:
        if entry.breaking and config.include_breaking:
            sections["breaking"].append(_entry_to_bullet(entry, audience))
        elif entry.type == "feat":
            sections["features"].append(_entry_to_bullet(entry, audience))
        elif entry.type == "fix" and config.include_fixes:
            sections["fixes"].append(_entry_to_bullet(entry, audience))
        else:
            sections["other"].append(_entry_to_bullet(entry, audience))

    lines = [f"# {release.version} Release Notes", "", intro, ""]

    for key in ("breaking", "features", "fixes", "other"):
        bullets = sections[key]
        if not bullets:
            continue
        lines += [f"## {headers[key]}", ""]
        lines += bullets
        lines.append("")

    return "\n".join(lines)


def generate_release_notes(
    from_ref: str,
    to_ref: str = "HEAD",
    version: str = "Unreleased",
    config: Optional[ReleaseNotesConfig] = None,
    repo: Optional[Path] = None,
) -> str:
    """Generate release notes between two git refs."""
    from datetime import date

    cfg = config or ReleaseNotesConfig()
    entries = get_commits_between(from_ref, to_ref, repo=repo)
    release = ChangelogRelease(
        version=version,
        release_date=date.today(),
        entries=entries,
    )
    return _render_release_notes(release, cfg)
