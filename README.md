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
| Nights active | 16 |
| Total PRs | 39 |
| Total commits | ~60 |
| Lines changed | ~22,000 |

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
| `src/cli.py` | Unified `nightshift` CLI with 38 subcommands |
| `src/refactor.py` | Self-refactor engine: AST analysis across 5 defect categories with auto-fix |
| `src/arch_generator.py` | Auto-generates docs/ARCHITECTURE.md from AST walk of the repo |
| `src/health_trend.py` | Tracks health scores across sessions; Unicode sparklines |
| `src/issue_triage.py` | Classifies + prioritizes GitHub issues (BUG/FEATURE/ENHANCEMENT/QUESTION/CHORE) |
| `src/brain.py` | Task prioritization engine: scores roadmap + issues for next session |
| `src/session_replay.py` | Reconstructs any past session from NIGHTSHIFT_LOG.md with narrative |
| `src/dep_graph.py` | AST-based directed module dependency graph; detects circular imports |
| `src/todo_hunter.py` | Scans TODO/FIXME/HACK/XXX annotations; flags items older than N sessions as stale |
| `src/doctor.py` | 13-check repo health diagnostic with A–F grade (CI, syntax, coverage, git status, etc.) |
| `src/timeline.py` | ASCII visual timeline of all Nightshift sessions from NIGHTSHIFT_LOG.md |
| `src/coupling.py` | Module coupling analyzer: Ca/Ce/instability per Robert Martin's stable-dependencies principle |
| `src/complexity.py` | AST-based McCabe cyclomatic complexity tracker with per-session history JSON |
| `src/exporter.py` | Export any analysis to JSON, Markdown, or self-contained dark-themed HTML |
| `src/config.py` | nightshift.toml config reader/writer with per-key defaults and validation |
| `src/compare.py` | Side-by-side session diff with stat deltas across PRs, tests, lines changed |
| `src/dashboard.py` | Rich terminal dashboard: box-drawing stats panel with sparklines |
| `src/deps_checker.py` | PyPI-based dependency freshness checker; flags outdated packages |
| `src/blame.py` | Git blame attribution: human vs AI contribution % per file and repo-wide |
| `src/dead_code.py` | AST-based dead code detector: unused functions, classes, and imports |
| `src/security.py` | Security audit: 10 checks for common Python anti-patterns, letter grade A–F |
| `src/coverage_map.py` | Test coverage heat map: cross-references src/X.py vs tests/test_X.py via AST |
| `src/story.py` | Narrative prose summary of the repo's evolution from NIGHTSHIFT_LOG.md |
| `src/maturity.py` | Module maturity scorer: tests, docs, complexity, age, coupling — 0–100 |
| `src/teach.py` | Tutorial generator: AST-based explanation of any module's structure and API |
| `src/dna.py` | Repo DNA fingerprint: 6-channel visual signature + deterministic hex digest |
| `src/benchmark.py` | Performance benchmark suite for all analysis modules with regression tracking |
| `src/gitstats.py` | Git statistics deep-dive: churn, velocity, commit frequency, PR size |
| `src/badges.py` | Shields.io README badge generator from live repo metrics |
| `src/server.py` | HTTP API server: 27 JSON endpoints for all analysis modules |
| `src/audit.py` | Comprehensive repo audit: weighted composite A–F grade (health+security+deadcode+coverage+complexity) |
| `src/semver.py` | Semantic version analyzer: Conventional Commits → major/minor/patch bump recommendation |
| `src/init_cmd.py` | Bootstrap scaffolding: idempotent project init with nightshift.toml, logs, CI workflow |
| `src/predict.py` | Predictive session planner: five-signal ranking of which modules need attention next |

## Tests

The test suite lives in `tests/`. Every module has a corresponding test file. All tests use stdlib only (no mocking frameworks, no fixtures beyond `tmp_path`).

```
pytest tests/
```

## License

MIT
