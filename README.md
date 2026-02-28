# 🌙 Nightshift

**AI submits PRs while you sleep.**

This repo is autonomously developed by [Perplexity Computer](https://perplexity.ai) overnight, every night. No human prompting during development sessions — the AI reads its own roadmap, picks tasks, writes code, runs tests, and opens pull requests.

Every morning, the human maintainer wakes up to a diff.

---

## How It Works

1. **11 PM CST** — Computer wakes up via scheduled task
2. **Survey** — Reads the full repo state, open issues, and its own roadmap
3. **Plan** — Autonomously decides what to build (2-5 improvements per session)
4. **Code** — Writes code locally, runs it, runs tests, iterates until passing
5. **Push** — Creates feature branches and opens PRs with detailed descriptions
6. **Log** — Appends a session summary to `NIGHTSHIFT_LOG.md`
7. **Sleep** — Waits for the next night

## Stats

| Metric | Count |
|--------|-------|
| Nights active | 4 |
| Total PRs | 13 |
| Total commits | 17 |
| Lines changed | 4100 |

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
| `src/pr_scorer.py` | Scores PRs 0–100 across 5 dimensions; grades A+–F; Markdown leaderboard |
| `src/cli.py` | Unified `nightshift` CLI tying all modules together (health/stats/diff/run) |
| `src/refactor.py` | Self-refactor engine: AST analysis across 5 defect categories with auto-fix |
| `src/arch_generator.py` | Auto-generates docs/ARCHITECTURE.md from AST walk of the repo |
| `src/health_trend.py` | Tracks health scores across sessions; Unicode sparklines + trend tables |

## Usage

```bash
# After pip install -e .
nightshift health          # code health score
nightshift stats           # repo stats
nightshift changelog       # render changelog
nightshift refactor        # find refactor candidates
nightshift run --session 4 # full end-of-session pipeline
```

## Project

Nightshift is a **self-improving autonomous development system**. The repo is both the project and the meta-project — Computer builds tools, then improves the tools it used to build them.

See [`ROADMAP.md`](ROADMAP.md) for what's planned.  
See [`NIGHTSHIFT_LOG.md`](NIGHTSHIFT_LOG.md) for what's happened.  
See [`.github/NIGHTSHIFT_RULES.md`](.github/NIGHTSHIFT_RULES.md) for the constraints.

## For Humans

Want the AI to build something? [Open an issue](../../issues/new) with the label `human-priority` and Computer will address it in the next overnight session.

---

*Built by [@gunnargray-dev](https://github.com/gunnargray-dev) and Perplexity Computer.*
