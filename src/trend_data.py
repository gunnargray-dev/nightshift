"""Trend data collection for Awake."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .utils import run_cmd


@dataclass
class TrendConfig:
    """Configuration for trend data collection."""

    db_path: Optional[Path] = None
    metrics: list[str] = field(
        default_factory=lambda: [
            "commit_count",
            "python_files",
            "test_files",
            "open_issues",
        ]
    )


_DEFAULT_DB = Path.home() / ".awake" / "trends.db"


def _ensure_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            metrics TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _collect_metrics(repo: Path, metric_names: list[str]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for metric in metric_names:
        if metric == "commit_count":
            try:
                out = run_cmd(["git", "rev-list", "--count", "HEAD"], cwd=repo)
                data[metric] = int(out.strip())
            except Exception:
                data[metric] = None
        elif metric == "python_files":
            data[metric] = len(list(repo.glob("**/*.py")))
        elif metric == "test_files":
            data[metric] = len(list(repo.glob("**/test_*.py"))) + len(
                list(repo.glob("**/*_test.py"))
            )
        elif metric == "open_issues":
            # Would call GitHub API in production
            data[metric] = None
        else:
            data[metric] = None
    return data


def record_trend_snapshot(
    repo: Path,
    config: Optional[TrendConfig] = None,
) -> dict[str, Any]:
    """Record a trend snapshot for *repo* and persist it to SQLite."""
    cfg = config or TrendConfig()
    db_path = cfg.db_path or _DEFAULT_DB
    conn = _ensure_db(db_path)

    metrics = _collect_metrics(repo, cfg.metrics)
    ts = datetime.utcnow().isoformat() + "Z"

    conn.execute(
        "INSERT INTO snapshots (repo, timestamp, metrics) VALUES (?, ?, ?)",
        (str(repo), ts, json.dumps(metrics)),
    )
    conn.commit()
    conn.close()

    return {
        "repo": str(repo),
        "timestamp": ts,
        "metrics": metrics,
        "db_path": str(db_path),
    }


def get_trend_history(
    repo: Path,
    config: Optional[TrendConfig] = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Retrieve trend history for *repo* from SQLite."""
    cfg = config or TrendConfig()
    db_path = cfg.db_path or _DEFAULT_DB
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT timestamp, metrics FROM snapshots WHERE repo = ? ORDER BY id DESC LIMIT ?",
        (str(repo), limit),
    ).fetchall()
    conn.close()
    return [
        {"timestamp": row[0], "metrics": json.loads(row[1])}
        for row in rows
    ]
