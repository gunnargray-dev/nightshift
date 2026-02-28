# 🌙 Nightshift

**AI submits PRs while you sleep.**

This repo is autonomously developed by [Perplexity Computer](https://perplexity.ai) overnight, every night. No human prompting during development sessions — the AI reads its own roadmap, picks tasks, writes code, runs tests, and opens pull requests.

Every morning, the human maintainer wakes up to a diff.

---

## How It Works

1. **11 PM CST** — Computer wakes up via scheduled task
2. **Survey** — Reads the full repo state, open issues, and its own roadmap
3. **Brain** — `src/brain.py` scores candidate tasks by impact, roadmap alignment, and health signals
4. **Code** — Writes code locally, runs it, runs tests, iterates until passing
5. **Push** — Creates feature branches and opens PRs with detailed descriptions
6. **Log** — Appends a session summary to `NIGHTSHIFT_LOG.md`
7. **Sleep** — Waits for the next night

## Stats

| Metric | Count |
|--------|-------|
| Nights active | 10 |
| Total PRs | 24 |
| Total commits | 30 |
| Lines changed | 8500 |

*Stats are updated by Computer each session.*

## Source Files

| Module | Description |
|--------|-------------|
| `src/stats.py` | Analyzes git history: commits, lines changed, session count, PR totals |
| `src/session_logger.py` | Structured `SessionEntry` renderer for NIGHTSHIFT_LOG.md |
| `src/health.py` | AST-based static analyzer scoring Python files 0–100 |
| `src/changelog.py` | Auto-generates CHANGELOG.md from `[nightshift]` commits grouped by session |
| `src/coverage_tracker.py` | Runs pytest-cov, stores history in JSON, renders trend table |
| `src/readme_updater.py` | Generates dynamic README.md from live repo state |
| `src/diff_visualizer.py` | Markdown summary of each night's git changes with block-bar heatmap |
| `src/pr_scorer.py` | Scores PRs 0–100 across 5 dimensions, grades A+–F, Markdown leaderboard |
| `src/cli.py` | Unified `nightshift` CLI with 12 subcommands |
| `src/refactor.py` | Self-refactor engine: AST analysis across 5 defect categories with auto-fix |
| `src/arch_generator.py` | Auto-generates docs/ARCHITECTURE.md from AST walk of the repo |
| `src/health_trend.py` | Tracks health scores across sessions; Unicode sparklines |
| `src/issue_triage.py` | Classifies + prioritizes GitHub issues (BUG/FEATURE/ENHANCEMENT/QUESTION/CHORE) |
| `src/brain.py` | Task prioritization engine: scores roadmap + issues for next session |
| `src/session_replay.py` | Reconstructs any past session from NIGHTSHIFT_LOG.md with narrative |
| `src/dep_graph.py` | AST-based directed module dependency graph; detects circular imports |
| `src/todo_hunter.py` | Scans TODO/FIXME/HACK/XXX annotations; flags items older than N sessions as stale |
| `src/doctor.py` | 13-check repo health diagnostic with A–F grade (CI, syntax, coverage, git status, etc.) |

## Usage

```bash
# After pip install -e .
nightshift health        # code health score
nightshift stats         # repo stats
nightshift changelog     # render changelog
nightshift diff          # last session diff
nightshift coverage      # coverage trend
nightshift score         # PR score leaderboard
nightshift arch --write  # regenerate docs/ARCHITECTURE.md
nightshift refactor      # refactor report
nightshift depgraph      # module dependency graph
nightshift todos         # scan stale TODOs
nightshift doctor        # repo health diagnostic (A-F grade)
nightshift run           # full pipeline
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
