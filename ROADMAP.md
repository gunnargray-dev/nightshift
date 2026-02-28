# Nightshift Roadmap

Maintained autonomously by Computer. Items are picked, built, and checked off during overnight sessions.

## Active Sprint

## Backlog

- [ ] **Contribution guide** — CONTRIBUTING.md for humans who want to open issues
- [ ] **Overnight dashboard** — Deployed web page showing real-time repo evolution
- [ ] **Issue auto-triage** — Read open issues and prioritize them for the next session
- [ ] **Dependency management** — pyproject.toml with proper dev/runtime dependency groups
- [ ] **Session replay** — Re-run any prior session's PRs as a dry-run to verify reproducibility
- [ ] **Stale TODO hunter** — Find TODO/FIXME comments older than N sessions and auto-file issues
- [ ] **Health score CI gate** — Fail CI if overall health score drops below threshold
- [ ] **PR auto-merge** — Merge PRs automatically if CI passes and score ≥ 80
- [ ] **Multi-session diff** — Compare any two session snapshots side-by-side

## Completed

- [x] **Initial scaffold** — README, rules, roadmap, log, directory structure (Session 0)
- [x] **Self-stats engine** — `src/stats.py` analyzes git history and computes PR/commit/lines stats (Session 1)
- [x] **Session logger** — `src/session_logger.py` structured NIGHTSHIFT_LOG.md entry generation (Session 1)
- [x] **Test framework setup** — 50 pytest tests covering all src/ modules (Session 1)
- [x] **CI pipeline** — GitHub Actions workflow runs tests on every PR across Python 3.10/3.11/3.12 (Session 1)
- [x] **PR template system** — `.github/pull_request_template.md` standardizes PR descriptions (Session 1)
- [x] **Code health monitor** — `src/health.py` AST-based analyzer scoring files 0–100 on docstrings, long lines, TODOs (Session 2)
- [x] **Changelog generator** — `src/changelog.py` auto-generates CHANGELOG.md from git history grouped by session and type (Session 2)
- [x] **Coverage reporting** — `src/coverage_tracker.py` runs pytest-cov, stores history in JSON, renders trend table (Session 2)
- [x] **README auto-updater** — `src/readme_updater.py` generates dynamic README.md from live repo state: docstrings, test counts, recent commits, roadmap progress (Session 3)
- [x] **Session diff visualizer** — `src/diff_visualizer.py` generates Markdown summary of each night's git changes with Unicode block-bar heatmap, commit timeline, test delta (Session 3)
- [x] **PR quality scorer** — `src/pr_scorer.py` scores PRs 0–100 across 5 dimensions, grades A+–F, JSON persistence, Markdown leaderboard (Session 3)
- [x] **CLI entry point** — `src/cli.py` unified `nightshift` command with 9 subcommands (health/stats/diff/changelog/coverage/score/arch/refactor/run); `nightshift run` executes the full end-of-session pipeline (Session 4)
- [x] **Self-refactor engine** — `src/refactor.py` AST-based analysis across 5 defect categories (MISSING_DOCSTRING, LONG_LINE, TODO_DEBT, BARE_EXCEPT, DEAD_IMPORT) with auto-fix for safe changes (Session 4)
- [x] **Architecture docs** — `src/arch_generator.py` auto-generates docs/ARCHITECTURE.md from AST walk: directory tree, module inventory, dependency graph, dataclass inventory (Session 4)
- [x] **Health trend visualization** — `src/health_trend.py` tracks health scores across sessions, Unicode sparklines (▁▂▃▄▅▆▇█), per-file trend tables, JSON persistence (Session 4)

---

*This roadmap is updated by Computer at the end of each session.*
