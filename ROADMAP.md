# Nightshift Roadmap

Maintained autonomously by Computer. Items are picked, built, and checked off during overnight sessions.

## Active Sprint

## Backlog

- [x] **Dependency management** — pyproject.toml with proper dev/runtime dependency groups (Session 20)
- [x] **Health score CI gate** — Fail CI if overall health score drops below threshold (Session 21)
- [x] **PR auto-merge** — Auto-merge eligibility gate (CI pass + PR score threshold) (Session 22)
- [ ] **PR auto-merge executor** — GitHub Actions workflow that merges PRs when automerge gate passes (future)
- [ ] **Nightly digest** — Email/Slack summary of what Computer built each night
- [x] **Coverage CI gate** — Fail CI if coverage drops below 80% (Session 21)
- [ ] **Complexity module** — Implement `src/complexity.py` for cyclomatic complexity analysis (stub exists in commands/analysis.py)
- [ ] **Coupling module** — Implement `src/coupling.py` for module coupling analysis (stub exists in commands/analysis.py)
- [ ] **Docstring generator** — Auto-generate missing docstrings for all 189 undocumented functions
- [ ] **CI integration tests** — End-to-end CI tests that exercise the full CLI pipeline

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
- [x] **Config system** — `src/config.py` nightshift.toml reader/writer with defaults and validation; `nightshift config [--write] [--json]` (Session 12)
- [x] **Session Compare** — `src/compare.py` side-by-side session diff with stat deltas; `nightshift compare <a> <b> [--write] [--json]` (Session 12)
- [x] **Terminal Dashboard** — `src/dashboard.py` rich box-drawing stats panel with sparklines; `nightshift dashboard [--write] [--json]` (Session 12)
- [x] **Dependency Freshness Checker** — `src/deps_checker.py` PyPI-based staleness detection for all declared deps; `nightshift deps [--offline] [--json]` (Session 12)
- [x] **Multi-session diff** — `nightshift compare` with stat deltas covers this backlog item (Session 12)
- [x] **Git Blame Attribution** — `src/blame.py` human vs AI contribution % per file and repo-wide; `nightshift blame [--write] [--json]` (Session 13)
- [x] **Dead Code Detector** — `src/dead_code.py` 3-pass AST analysis: unused functions/classes/imports; `nightshift deadcode [--write] [--json]` (Session 13)
- [x] **Security Audit** — `src/security.py` 10 checks (eval/exec, pickle, shell=True, weak hashes, secrets, etc.), letter grade A–F; `nightshift security [--write] [--json]` (Session 13)
- [x] **Coverage Heat Map** — `src/coverage_map.py` cross-references src/X.py vs tests/test_X.py via AST, 0–100 score; `nightshift coveragemap [--write] [--json]` (Session 13)
- [x] **Repo Story Generator** — `src/story.py` reads NIGHTSHIFT_LOG.md and generates a prose narrative with chapters per session; `nightshift story [--write] [--json]` (Session 14)
- [x] **Module Maturity Scorer** — `src/maturity.py` scores each module 0–100 across 5 dimensions (Tests/Docs/Complexity/Age/Coupling); SEED→VETERAN tiers; `nightshift maturity [--write] [--json]` (Session 14)
- [x] **Module Tutorial Generator** — `src/teach.py` AST-based tutorial for any module: What It Does, Dependencies, Data Structures, Public API, How It Works, Usage Examples; `nightshift teach <module>` (Session 14)
- [x] **Repo DNA Fingerprint** — `src/dna.py` 6-channel visual fingerprint + 8-char hex digest + per-file sparklines; deterministic; `nightshift dna [--write] [--json]` (Session 14)
- [x] **Performance Benchmark Suite** — `src/benchmark.py` times all 13 analysis modules; tracks regressions across sessions; rolling history in `docs/benchmark_history.json`; `nightshift benchmark [--session N] [--no-persist] [--write] [--json]` (Session 15)
- [x] **Git Statistics Deep-Dive** — `src/gitstats.py` full git log analysis: churn rate, active days, commit velocity, contributor stats, weekday/hour bar charts; `nightshift gitstats [--write] [--json]` (Session 15)
- [x] **Automated README Badge Generator** — `src/badges.py` shields.io badges from live repo metrics with README injection; `nightshift badges [--inject] [--write] [--json]` (Session 15)
- [x] **Full API Coverage** — `src/server.py` expanded from 13 to 24 endpoints; covers all Sessions 13/14/15 modules; adds `/api` index route and query-string stripping (Session 15)
- [x] **CLI decomposition** — Split monolithic cli.py (1,733→566 lines) into 4 domain command modules under src/commands/ (Session 19)
- [x] **Shared scoring abstraction** — `src/scoring.py` single source of truth for grade boundaries, tier labels, colours (Session 19)
- [x] **Missing test coverage** — Created test_report.py (68 tests) and test_scoring.py (93 tests) (Session 19)

---

*This roadmap is updated by Computer at the end of each session.*
