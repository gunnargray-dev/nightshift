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
| Nights active | 15 |
| Total PRs | 38 |
| Total commits | 54 |
| Lines changed | 20000 |

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
| `src/cli.py` | Unified `nightshift` CLI with 34 subcommands |
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
| `src/story.py` | Reads NIGHTSHIFT_LOG.md and generates a prose narrative of repo evolution with chapters per session |
| `src/maturity.py` | Scores each module 0–100 across 5 dimensions (Tests, Docs, Complexity, Age, Coupling); SEED→VETERAN tiers |
| `src/teach.py` | AST-based tutorial generator: produces a full written tutorial for any module in the repo |
| `src/dna.py` | 6-channel visual DNA fingerprint of the repo with 8-char hex digest and per-file sparklines |
| `src/benchmark.py` | Performance benchmark suite: times all 13 analysis modules, tracks regressions across sessions |
| `src/gitstats.py` | Git statistics deep-dive: churn rate, commit velocity, contributor stats, weekday/hour bar charts |
| `src/badges.py` | Automated README badge generator: shields.io badges from live repo metrics, injects into README |

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
nightshift timeline      # ASCII visual session timeline
nightshift coupling      # module coupling (Ca/Ce/instability)
nightshift complexity    # cyclomatic complexity tracker
nightshift export coupling --formats json,html  # export any analysis
nightshift config        # show/write nightshift.toml
nightshift compare 11 12 # diff two sessions side-by-side
nightshift dashboard     # rich terminal dashboard
nightshift deps          # check dependency freshness
nightshift blame         # human vs AI attribution
nightshift deadcode      # detect unused code
nightshift security      # security audit (A-F grade)
nightshift coveragemap   # test coverage heat map
nightshift story         # prose narrative of repo evolution
nightshift maturity      # module maturity scores (SEED→VETERAN)
nightshift teach <mod>   # generate tutorial for any module
nightshift dna           # repo DNA fingerprint with hex digest
nightshift benchmark     # performance benchmark all modules
nightshift gitstats      # git statistics deep-dive (churn, velocity)
nightshift badges        # generate shields.io README badges
nightshift run           # full pipeline
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
