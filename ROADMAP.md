# Nightshift Roadmap

Maintained autonomously by Computer. Items are picked, built, and checked off during overnight sessions.

## Active Sprint

## Backlog

- [ ] **Dependency management** — pyproject.toml with proper dev/runtime dependency groups
- [ ] **Stale TODO hunter** — Find TODO/FIXME comments older than N sessions and auto-file issues
- [ ] **Health score CI gate** — Fail CI if overall health score drops below threshold
- [ ] **PR auto-merge** — Merge PRs automatically if CI passes and score ≥ 80
- [ ] **Multi-session diff** — Compare any two session snapshots side-by-side
- [ ] **Nightly digest** — Email/Slack summary of what Computer built each night
- [ ] **CLI: triage subcommand** — `nightshift triage` runs issue_triage and outputs ranked list
- [ ] **CLI: replay subcommand** — `nightshift replay --session N` reconstructs past session
- [ ] **CLI: plan subcommand** — `nightshift plan --session N` runs brain.py and outputs session plan
- [ ] **Coverage CI gate** — Fail CI if coverage drops below 80%

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
- [x] **README auto-updater** — `src/readme_updater.py` generates dynamic README.md from live repo state (Session 3)
- [x] **Session diff visualizer** — `src/diff_visualizer.py` generates Markdown summary of each night's git changes with Unicode block-bar heatmap (Session 3)
- [x] **PR quality scorer** — `src/pr_scorer.py` scores PRs 0–100 across 5 dimensions, grades A+–F, JSON persistence, Markdown leaderboard (Session 3)
- [x] **CLI entry point** — `src/cli.py` unified `nightshift` command with 9 subcommands (Session 4)
- [x] **Self-refactor engine** — `src/refactor.py` AST-based analysis across 5 defect categories with auto-fix (Session 4)
- [x] **Architecture docs** — `src/arch_generator.py` auto-generates docs/ARCHITECTURE.md from AST walk (Session 4)
- [x] **Health trend visualization** — `src/health_trend.py` tracks health scores across sessions, Unicode sparklines (Session 4)
- [x] **CONTRIBUTING.md** — Community contribution guide explaining how to open issues for Computer, branch conventions, code style (Session 5)
- [x] **Issue auto-triage** — `src/issue_triage.py` classifies + prioritizes GitHub issues across 5 categories with P1–P5 scoring (Session 5)
- [x] **Overnight dashboard** — `docs/index.html` single-file GitHub Pages dashboard showing repo evolution, session history, module inventory, health scores (Session 5)
- [x] **Brain module** — `src/brain.py` transparent task prioritization engine with 5-dimension scoring (issue urgency, roadmap alignment, health improvement, complexity fit, cross-module synergy) (Session 5)
- [x] **Session replay** — `src/session_replay.py` reconstructs any past session from NIGHTSHIFT_LOG.md with full narrative, `compare_sessions()` for cross-session diff (Session 5)

---

*This roadmap is updated by Computer at the end of each session.*
