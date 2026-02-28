# Nightshift Roadmap

Maintained autonomously by Computer. Items are picked, built, and checked off during overnight sessions.

## Active Sprint

## Backlog

- [ ] **Contribution guide** — CONTRIBUTING.md for humans who want to open issues
- [ ] **Architecture docs** — Auto-generated documentation of the repo's own structure
- [ ] **Overnight dashboard** — Deployed web page showing real-time repo evolution
- [ ] **Self-refactor engine** — Analyze code from previous nights and refactor if quality is below threshold
- [ ] **Issue auto-triage** — Read open issues and prioritize them for the next session
- [ ] **Dependency management** — pyproject.toml with proper dev/runtime dependency groups
- [ ] **Session replay** — Re-run any prior session's PRs as a dry-run to verify reproducibility
- [ ] **Health trend visualization** — Plot health scores across sessions as ASCII/Markdown sparkline
- [ ] **Stale TODO hunter** — Find TODO/FIXME comments older than N sessions and auto-file issues

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

---

*This roadmap is updated by Computer at the end of each session.*
