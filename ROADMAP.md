# Nightshift Roadmap

Maintained autonomously by Computer. Items are picked, built, and checked off during overnight sessions.

## Active Sprint

_Session 12 complete. Next: Session 13._

## Backlog

- [ ] **Dependency management** — pyproject.toml with proper dev/runtime dependency groups
- [ ] **Health score CI gate** — Fail CI if overall health score drops below threshold
- [ ] **PR auto-merge** — Merge PRs automatically if CI passes and score ≥ 80
- [ ] **Multi-session diff** — Compare any two session snapshots side-by-side
- [ ] **Nightly digest** — Email/Slack summary of what Computer built each night
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
- [x] **CI fix + session_replay regex** — Fixed `\)*` branch-parsing regex; all 584 tests pass on Python 3.10/3.11/3.12 (Session 10)
- [x] **Module dependency graph** — `src/dep_graph.py` AST-based directed graph of src/ imports; detects circular deps, computes in/out degree (Session 10)
- [x] **Stale TODO hunter** — `src/todo_hunter.py` scans TODO/FIXME/HACK/XXX, parses session annotations, flags stale items (Session 10)
- [x] **Nightshift Doctor** — `src/doctor.py` 13-check repo health diagnostic with A–F grade (CI, syntax, coverage, docstrings, git status, etc.) (Session 10)
- [x] **CLI expanded to 12 subcommands** — `nightshift depgraph`, `nightshift todos`, `nightshift doctor` added (Session 10)
- [x] **Session Timeline** — `src/timeline.py` ASCII visual timeline of all sessions from NIGHTSHIFT_LOG.md; `nightshift timeline [--write] [--json]` (Session 11)
- [x] **Module Coupling Analyzer** — `src/coupling.py` Ca/Ce/instability per Robert Martin's stable-dependencies principle; `nightshift coupling [--write] [--json]` (Session 11)
- [x] **Cyclomatic Complexity Tracker** — `src/complexity.py` AST-based McCabe complexity with per-session history JSON; `nightshift complexity [--session N] [--write]` (Session 11)
- [x] **Export System** — `src/exporter.py` JSON/Markdown/HTML export for any analysis with dark-themed self-contained HTML; `nightshift export <analysis>` (Session 11)

- [x] **Config system** — `src/config.py` reads/writes `nightshift.toml`; `NightshiftConfig` dataclass; stdlib TOML parser; `nightshift config [--write] [--json]` (Session 12)
- [x] **Session compare** — `src/compare.py` side-by-side session diff with stat deltas, task diffs, bar charts; `nightshift compare <a> <b> [--write] [--json]` (Session 12)
- [x] **Terminal dashboard** — `src/dashboard.py` box-drawing stats panel; 4 stat cards; SOURCE/METRICS/RECENT SESSIONS panels; sparklines; `nightshift dashboard [--write] [--json]` (Session 12)
- [x] **Dependency freshness checker** — `src/deps_checker.py` queries PyPI JSON API for outdated packages; `nightshift deps [--offline] [--json]` (Session 12)

---

*This roadmap is updated by Computer at the end of each session.*
