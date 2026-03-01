"""Automated README badge generator for Awake.

Generates shields.io badges for key repo metrics: test count, health score,
session count, security grade, and maturity average.  Badges can be written
directly to README.md or returned as a Markdown snippet.

Usage
-----
    from src.badges import generate_badges, write_badges_to_readme
    badge_block = generate_badges(repo_path=Path("."))
    print(badge_block.to_markdown())
    write_badges_to_readme(badge_block, repo_path=Path("."))
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from src.scoring import grade_colour as _grade_colour_hex, score_colour as _score_colour_hex


def _shields_static(label: str, message: str, color: str, style: str = "flat-square") -> str:
    label_enc = label.replace(" ", "%20").replace("-", "--").replace("_", "__")
    message_enc = message.replace(" ", "%20").replace("-", "--").replace("_", "__")
    return (f"![{label}](https://img.shields.io/badge/"
            f"{label_enc}-{message_enc}-{color}?style={style})")


def _grade_color(grade: str) -> str:
    """Return a shields.io colour name for a letter *grade*."""
    grade = grade.strip().upper()
    if grade.startswith("A"): return "brightgreen"
    if grade.startswith("B"): return "green"
    if grade.startswith("C"): return "yellow"
    if grade.startswith("D"): return "orange"
    return "red"


def _score_color(score: float) -> str:
    """Return a shields.io colour name for a numeric 0–100 *score*."""
    return _score_colour_hex(score, shields=True)


@dataclass
class Badge:
    """A single shield badge."""
    label: str
    message: str
    color: str
    alt: str = ""

    def to_markdown(self) -> str:
        """Render this badge as a Markdown image link for shields.io."""
        alt = self.alt or self.label
        label_enc = self.label.replace(" ", "%20").replace("-", "--").replace("_", "__")
        msg_enc = self.message.replace(" ", "%20").replace("-", "--").replace("_", "__")
        return (f"![{alt}](https://img.shields.io/badge/"
                f"{label_enc}-{msg_enc}-{self.color}?style=flat%2Dsquare)")

    def to_dict(self) -> dict:
        """Serialise this badge to a plain dictionary."""
        return asdict(self)


@dataclass
class BadgeBlock:
    """Collection of badges for the repo."""
    badges: list[Badge] = field(default_factory=list)
    generated_at: str = ""

    def to_markdown(self) -> str:
        """Render all badges as a single space-separated Markdown string."""
        return "  ".join(b.to_markdown() for b in self.badges)

    def to_markdown_block(self) -> str:
        """Render all badges as a Markdown string with a trailing newline."""
        return self.to_markdown() + "\n"

    def to_json(self) -> str:
        """Serialise the badge block to a pretty-printed JSON string."""
        return json.dumps(
            {"badges": [b.to_dict() for b in self.badges], "generated_at": self.generated_at},
            indent=2,
        )

    def to_dict(self) -> dict:
        """Serialise the badge block to a plain dictionary (JSON-safe)."""
        return {"badges": [b.to_dict() for b in self.badges], "generated_at": self.generated_at}


def _get_session_count(repo_path: Path) -> int:
    log = repo_path / "AWAKE_LOG.md"
    if not log.exists(): return 0
    text = log.read_text(errors="replace")
    return len(re.findall(r"^## Session \d+", text, re.MULTILINE))


def _get_test_count(repo_path: Path) -> int:
    tests_dir = repo_path / "tests"
    if not tests_dir.exists(): return 0
    count = 0
    for py_file in tests_dir.glob("test_*.py"):
        try:
            text = py_file.read_text(errors="replace")
            count += len(re.findall(r"^\s*def test_", text, re.MULTILINE))
        except Exception:
            pass
    return count


def _get_health_score(repo_path: Path) -> Optional[float]:
    try:
        from src.health import analyze_health
        report = analyze_health(repo_path / "src")
        return report.average_score
    except Exception:
        return None


def _get_security_grade(repo_path: Path) -> Optional[str]:
    try:
        from src.security import audit_security
        report = audit_security(repo_path / "src")
        return report.grade
    except Exception:
        return None


def _get_module_count(repo_path: Path) -> int:
    src_dir = repo_path / "src"
    if not src_dir.exists(): return 0
    return len([f for f in src_dir.glob("*.py") if not f.name.startswith("_")])


def _get_maturity_avg(repo_path: Path) -> Optional[float]:
    try:
        from src.maturity import assess_maturity
        report = assess_maturity(repo_path=repo_path)
        return report.avg_score
    except Exception:
        return None


def _get_pr_count(repo_path: Path) -> int:
    log = repo_path / "AWAKE_LOG.md"
    if not log.exists(): return 0
    text = log.read_text(errors="replace")
    prs = re.findall(r"\[#(\d+)\]\(https://github\.com/[^)]+/pull/\d+\)", text)
    return max(int(p) for p in prs) if prs else 0


def generate_badges(repo_path: Optional[Path] = None) -> BadgeBlock:
    """Collect metrics and build a BadgeBlock."""
    import datetime
    repo = repo_path or Path(__file__).resolve().parent.parent
    badges: list[Badge] = []

    sessions = _get_session_count(repo)
    badges.append(Badge(label="sessions", message=str(sessions), color="blueviolet",
                        alt="Awake Sessions"))

    pr_count = _get_pr_count(repo)
    if pr_count:
        badges.append(Badge(label="PRs", message=str(pr_count), color="blue", alt="Total PRs"))

    test_count = _get_test_count(repo)
    if test_count:
        t_color = "brightgreen" if test_count >= 500 else "green" if test_count >= 200 else "yellow"
        badges.append(Badge(label="tests", message=f"{test_count:,}", color=t_color, alt="Test Count"))

    module_count = _get_module_count(repo)
    if module_count:
        badges.append(Badge(label="modules", message=str(module_count), color="informational",
                            alt="Module Count"))

    health = _get_health_score(repo)
    if health is not None:
        badges.append(Badge(label="health", message=f"{health:.0f}%2F100",
                            color=_score_color(health), alt="Health Score"))

    sec_grade = _get_security_grade(repo)
    if sec_grade:
        badges.append(Badge(label="security", message=sec_grade,
                            color=_grade_color(sec_grade), alt="Security Grade"))

    maturity = _get_maturity_avg(repo)
    if maturity is not None:
        badges.append(Badge(label="maturity", message=f"{maturity:.0f}%2F100",
                            color=_score_color(maturity), alt="Avg Maturity"))

    badges.append(Badge(label="python", message="3.10%2B", color="3776AB", alt="Python Version"))
    badges.append(Badge(label="license", message="MIT", color="lightgrey", alt="License"))

    return BadgeBlock(
        badges=badges,
        generated_at=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )


_BADGE_SECTION_START = "<!-- badges:start -->"
_BADGE_SECTION_END = "<!-- badges:end -->"


def write_badges_to_readme(block: BadgeBlock, repo_path: Optional[Path] = None) -> bool:
    """Inject badge block between marker comments in README.md.

    Returns True if README was modified, False otherwise.
    """
    repo = repo_path or Path(__file__).resolve().parent.parent
    readme = repo / "README.md"
    if not readme.exists(): return False
    text = readme.read_text()
    badge_line = block.to_markdown_block()

    if _BADGE_SECTION_START in text and _BADGE_SECTION_END in text:
        new_text = re.sub(
            re.escape(_BADGE_SECTION_START) + r".*?" + re.escape(_BADGE_SECTION_END),
            f"{_BADGE_SECTION_START}\n{badge_line.strip()}\n{_BADGE_SECTION_END}",
            text, flags=re.DOTALL,
        )
        readme.write_text(new_text)
        return True

    h1_match = re.search(r"^# .+", text, re.MULTILINE)
    if h1_match:
        insert_pos = h1_match.end()
        new_text = (
            text[:insert_pos] + "\n\n" + _BADGE_SECTION_START + "\n"
            + badge_line.strip() + "\n" + _BADGE_SECTION_END + text[insert_pos:]
        )
        readme.write_text(new_text)
        return True
    return False


def save_badges_report(block: BadgeBlock, output_path: Path) -> None:
    """Write a Markdown badges report and JSON sidecar to *output_path*."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    md = "# Awake Badges\n\n"
    md += f"*Generated: {block.generated_at}*\n\n"
    md += "## Badge Preview\n\n" + block.to_markdown_block() + "\n\n"
    md += "## Raw Markdown\n\n```markdown\n" + block.to_markdown_block() + "```\n\n"
    md += "## Badge Details\n\n| Label | Message | Color |\n|-------|---------|-------|\n"
    for b in block.badges:
        md += f"| {b.label} | {b.message} | {b.color} |\n"
    output_path.write_text(md)
    output_path.with_suffix(".json").write_text(block.to_json())
