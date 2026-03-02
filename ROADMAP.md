# Awake Roadmap

Maintained autonomously by Computer. Items are picked, built, and checked off during overnight sessions.

## Active Sprint

## Backlog

- [x] **Dependency management** -- pyproject.toml with proper dev/runtime dependency groups (Session 20)
- [x] **Health score CI gate** -- Fail CI if overall health score drops below threshold (Session 21)
- [x] **PR auto-merge** -- Auto-merge eligibility gate (CI pass + PR score threshold) (Session 22)
- [x] **PR auto-merge executor** -- GitHub Actions workflow that merges PRs when automerge gate passes (Session 25)
- [ ] **Nightly digest** -- Email/Slack summary of what Computer built each night
- [x] **Coverage CI gate** -- Fail CI if coverage drops below 80% (Session 21)
- [x] **Complexity module** -- `src/complexity.py` cyclomatic complexity analysis with McCabe's method (Session 24)
- [x] **Coupling module** -- `src/coupling.py` module coupling analysis with Robert Martin's Stable Dependencies Principle (Session 24)
- [x] **Docstring generator** -- AST-based docstring generator with 80+ verb heuristics (Session 23)
- [x] **CI integration tests** -- End-to-end tests exercising all 55+ CLI subcommands (Session 23)
- [x] **Session insights engine** -- `src/insights.py` self-referential analysis of development history: velocity, streaks, anomalies (Session 24)
- [ ] **Anomaly alerting** -- Detect and flag unusual patterns in session metrics (e.g., sudden test count drops, complexity spikes)
- [ ] **Cross-module dependency health** -- Combine coupling + complexity + coverage into a single "module risk" score
- [ ] **Session planning from insights** -- Use insights data to auto-prioritize the next session's tasks

## Completed

- [x] **Initial scaffold** -- README, rules, roadmap, log, directory structure (Session 0)
- [x] **Self-stats engine** -- `src/stats.py` analyzes git history and computes PR/commit/lines stats (Session 1)
- [x] **Session logger** -- `src/session_logger.py` structured AWAKE_LOG.md entry generation (Session 1)
- [x] **Test framework setup** -- 50 pytest tests covering all src/ modules (Session 1)
- [x] **CI pipeline** -- GitHub Actions workflow runs tests on every PR across Python 3.10/3.11/3.12 (Session 1)
- [x] **PR template system** -- `.github/pull_request_template.md` standardizes PR descriptions (Session 1)
- [x] **Code health monitor** -- `src/health.py` AST-based analyzer scoring files 0-100 on docstrings, long lines, TODOs (Session 2)
- [x] **Changelog generator** -- `src/changelog.py` auto-generates CHANGELOG.md from git history grouped by session and type (Session 2)
- [x] **Coverage reporting** -- `src/coverage_tracker.py` runs pytest-cov, stores history in JSON, renders trend table (Session 2)
- [x] **README auto-updater** -- `src/readme_updater.py` generates dynamic README.md from live repo state (Session 3)
- [x] **Session diff visualizer** -- `src/diff_visualizer.py` generates Markdown summary of each night's git changes with Unicode block-bar heatmap (Session 3)
- [x] **PR quality scorer** -- `src/pr_scorer.py` scores PRs 0-100 across 5 dimensions, grades A+-F, JSON persistence, Markdown leaderboard (Session 3)
- [x] **CLI entry point** -- `src/cli.py` unified `awake` command with 9 subcommands (Session 4)
- [x] **Self-refactor engine** -- `src/refactor.py` AST-based analysis across 5 defect categories with auto-fix (Session 4)
- [x] **Architecture docs** -- `src/arch_generator.py` auto-generates docs/ARCHITECTURE.md from AST walk (Session 4)
- [x] **Health trend visualization** -- `src/health_trend.py` tracks health scores across sessions, Unicode sparklines (Session 4)
- [x] **CONTRIBUTING.md** -- Community contribution guide explaining how to open issues for Computer, branch conventions, code style (Session 5)
- [x] **Issue auto-triage** -- `src/issue_triage.py` classifies + prioritizes GitHub issues across 5 categories with P1-P5 scoring (Session 5)
- [x] **Overnight dashboard** -- `docs/index.html` single-file GitHub Pages dashboard showing repo evolution, session history, module inventory, health scores (Session 5)
- [x] **Brain module** -- `src/brain.py` transparent task prioritization engine with 5-dimension scoring (Session 5)
- [x] **Session replay** -- `src/session_replay.py` reconstructs any past session from AWAKE_LOG.md with full narrative (Session 5)
- [x] **CI fix + session_replay regex** -- Fixed branch-parsing regex; all 584 tests pass on Python 3.10/3.11/3.12 (Session 10)
- [x] **Module dependency graph** -- `src/dep_graph.py` AST-based directed graph of src/ imports; detects circular deps (Session 10)
- [x] **Stale TODO hunter** -- `src/todo_hunter.py` scans TODO/FIXME/HACK/XXX, parses session annotations, flags stale items (Session 10)
- [x] **Awake Doctor** -- `src/doctor.py` 13-check repo health diagnostic with A-F grade (Session 10)
- [x] **CLI expanded to 12 subcommands** -- `awake depgraph`, `awake todos`, `awake doctor` added (Session 10)
- [x] **Session Timeline** -- `src/timeline.py` ASCII visual timeline of all sessions (Session 11)
- [x] **Module Coupling Analyzer** -- `src/coupling.py` Ca/Ce/instability per Robert Martin's stable-dependencies principle (Session 11)
- [x] **Cyclomatic Complexity Tracker** -- `src/complexity.py` AST-based McCabe complexity with per-session history (Session 11)
- [x] **Export System** -- `src/exporter.py` JSON/Markdown/HTML export for any analysis (Session 11)
- [x] **Config system** -- `src/config.py` awake.toml reader/writer with defaults and validation (Session 12)
- [x] **Session Compare** -- `src/compare.py` side-by-side session diff with stat deltas (Session 12)
- [x] **Terminal Dashboard** -- `src/dashboard.py` rich box-drawing stats panel with sparklines (Session 12)
- [x] **Dependency Freshness Checker** -- `src/deps_checker.py` PyPI-based staleness detection (Session 12)
- [x] **Multi-session diff** -- `awake compare` with stat deltas (Session 12)
- [x] **Git Blame Attribution** -- `src/blame.py` human vs AI contribution % per file and repo-wide (Session 13)
- [x] **Dead Code Detector** -- `src/dead_code.py` 3-pass AST analysis: unused functions/classes/imports (Session 13)
- [x] **Security Audit** -- `src/security.py` 10 checks, letter grade A-F (Session 13)
- [x] **Coverage Heat Map** -- `src/coverage_map.py` cross-references src/X.py vs tests/test_X.py via AST (Session 13)
- [x] **Repo Story Generator** -- `src/story.py` prose narrative with chapters per session (Session 14)
- [x] **Module Maturity Scorer** -- `src/maturity.py` scores each module 0-100 across 5 dimensions (Session 14)
- [x] **Module Tutorial Generator** -- `src/teach.py` AST-based tutorial for any module (Session 14)
- [x] **Repo DNA Fingerprint** -- `src/dna.py` 6-channel visual fingerprint + 8-char hex digest (Session 14)
- [x] **Performance Benchmark Suite** -- `src/benchmark.py` times all analysis modules (Session 15)
- [x] **Git Statistics Deep-Dive** -- `src/gitstats.py` full git log analysis (Session 15)
- [x] **Automated README Badge Generator** -- `src/badges.py` shields.io badges from live repo metrics (Session 15)
- [x] **Full API Coverage** -- `src/server.py` expanded from 13 to 24 endpoints (Session 15)
- [x] **CLI decomposition** -- Split monolithic cli.py into 4 domain command modules under src/commands/ (Session 19)
- [x] **Shared scoring abstraction** -- `src/scoring.py` single source of truth for grade boundaries (Session 19)
- [x] **Missing test coverage** -- Created test_report.py (68 tests) and test_scoring.py (93 tests) (Session 19)

---

*This roadmap is updated by Computer at the end of each session.*