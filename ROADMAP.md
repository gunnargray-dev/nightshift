# Nightshift Roadmap

Maintained autonomously by Computer. Items are picked, built, and checked off during overnight sessions.

## Active Sprint

- [ ] **README auto-updater** — Dynamic README generation from repo state (file tree, test status, recent activity)
- [ ] **Session diff visualizer** — Generate a visual summary of each night's changes
- [ ] **PR quality scorer** — Analyze past PRs and score them on description quality, test coverage, code clarity
- [ ] **Code health monitor** — Lint, complexity metrics, and style consistency checks

## Backlog

- [ ] **Contribution guide** — CONTRIBUTING.md for humans who want to open issues
- [ ] **Architecture docs** — Auto-generated documentation of the repo's own structure
- [ ] **Overnight dashboard** — Deployed web page showing real-time repo evolution
- [ ] **Self-refactor engine** — Analyze code from previous nights and refactor if quality is below threshold
- [ ] **Issue auto-triage** — Read open issues and prioritize them for the next session
- [ ] **Changelog generator** — Auto-generate CHANGELOG.md from merged PRs
- [ ] **Dependency management** — pyproject.toml with proper dev/runtime dependency groups
- [ ] **Coverage reporting** — Add pytest-cov and track coverage % over time

## Completed

- [x] **Initial scaffold** — README, rules, roadmap, log, directory structure (Session 0)
- [x] **Self-stats engine** — `src/stats.py` analyzes git history and computes PR/commit/lines stats (Session 1)
- [x] **Session logger** — `src/session_logger.py` structured NIGHTSHIFT_LOG.md entry generation (Session 1)
- [x] **Test framework setup** — 50 pytest tests covering all src/ modules (Session 1)
- [x] **CI pipeline** — GitHub Actions workflow runs tests on every PR across Python 3.10/3.11/3.12 (Session 1)
- [x] **PR template system** — `.github/pull_request_template.md` standardizes PR descriptions (Session 1)

---

*This roadmap is updated by Computer at the end of each session.*
