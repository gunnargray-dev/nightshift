# Nightshift

<!-- badges:start -->
[![Sessions](https://img.shields.io/badge/sessions-19-blueviolet?style=flat-square)](https://github.com/gunnargray-dev/nightshift/blob/main/NIGHTSHIFT_LOG.md)
[![PRs](https://img.shields.io/badge/PRs-42-blue?style=flat-square)](https://github.com/gunnargray-dev/nightshift/pulls)
[![Tests](https://img.shields.io/badge/tests-2128%2B-brightgreen?style=flat-square)](https://github.com/gunnargray-dev/nightshift/tree/main/tests)
[![Modules](https://img.shields.io/badge/modules-61-orange?style=flat-square)](https://github.com/gunnargray-dev/nightshift/tree/main/src)
[![CLI](https://img.shields.io/badge/CLI_commands-50-cyan?style=flat-square)](https://github.com/gunnargray-dev/nightshift/blob/main/src/cli.py)
[![API](https://img.shields.io/badge/API_endpoints-39-teal?style=flat-square)](https://github.com/gunnargray-dev/nightshift/blob/main/src/server.py)
[![Python](https://img.shields.io/badge/python-3.10%2B-yellow?style=flat-square)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-lightgrey?style=flat-square)](LICENSE)
<!-- badges:end -->

> **An AI that improves its own codebase — autonomously, every session.**

Nightshift is a self-improving autonomous development system. An AI runs overnight, analyzes the repo, identifies what matters most, ships features, writes tests, and opens a pull request — all without human input. Then it does it again the next session, learning from what it built.

**19 sessions. 42 PRs. 61 modules. 2,128+ tests. Zero human commits.**

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────────┐
│                        NIGHTSHIFT PIPELINE                          │
│                                                                     │
│   1. ANALYZE          2. DECIDE           3. BUILD                  │
│   ──────────         ──────────          ───────                    │
│                                                                     │
│   nightshift stats ──► brain.py      ──► write code                │
│   nightshift health    (5-dimension       write tests               │
│   nightshift audit     scoring:           update CLI                │
│   nightshift predict   · complexity       update API                │
│   nightshift dna       · coverage                                   │
│                        · churn         4. VERIFY                    │
│                        · debt          ───────                      │
│                        · momentum)     pytest (all green)           │
│                             │                                       │
│                             ↓          5. SHIP                      │
│                         ranked task    ──────                       │
│                         queue          git commit                   │
│                                        open PR                      │
│                                        update log                   │
└─────────────────────────────────────────────────────────────────────┘

  METACOGNITION LAYER (new in Session 18)
  ────────────────────────────────────────
  nightshift reflect  ──► analyzes ALL past sessions, scores quality,
                          identifies patterns, surfaces what the AI
                          learned and how it has improved over time

  nightshift evolve   ──► gap analysis + next evolution proposals
                          based on system's own growth trajectory

  nightshift status   ──► one-command comprehensive health snapshot
```

The system is entirely self-contained. Every module is pure Python stdlib — no runtime dependencies. The AI reads `NIGHTSHIFT_LOG.md` as memory, uses `brain.py` as its decision engine, and leaves behind a PR as evidence of its work.

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/gunnargray-dev/nightshift
cd nightshift
pip install -e .

# Run a health check
nightshift health

# See what the AI would do next
nightshift brain

# View the full status dashboard (new in Session 18)
nightshift status

# Launch the React dashboard
nightshift dashboard
# → http://localhost:5173

# Read the AI's self-analysis
nightshift reflect

# Ask the AI what it should become
nightshift evolve
```

---

## Feature Showcase

### Intelligence Core

The brain is a five-dimension scoring engine. Every module in the codebase gets scored against five independent signals, and the results are ranked into a prioritized action queue for the next session.

```
$ nightshift brain

  BRAIN ANALYSIS — Session 18 context
  ─────────────────────────────────────────────────────

  Signal weights:
    Complexity drift    25%   (McCabe complexity trends)
    Coverage weakness   25%   (test gap by module)
    Module age          20%   (time since last touch)
    TODO debt           15%   (unresolved markers)
    Health trend        15%   (rolling score delta)

  Top candidates for next session:
    1. security.py         score: 87   [complexity + coverage]
    2. refactor.py         score: 81   [age + debt]
    3. coverage_tracker.py score: 74   [coverage weakness]
```

### Metacognition (Session 18)

The system can now reflect on its own history — scoring past sessions, identifying productivity patterns, and proposing its own evolution.

```
$ nightshift reflect

  SESSION META-ANALYSIS
  ─────────────────────────────────────────────────────
  Analyzing 18 sessions across 5 quality dimensions...

  Most productive sessions:
    Session 14   score: 94/100   [4 modules, 254 tests, DNA + Maturity]
    Session 17   score: 91/100   [9 modules, 160 tests, plugin + OpenAPI]
    Session 15   score: 88/100   [3 modules, 155 tests, benchmark suite]

  Patterns discovered:
    · Sessions with clear themes outperform unfocused ones by 34%
    · Test count is the strongest predictor of session quality
    · Feature velocity has increased 2.3x from sessions 1–6 to 13–18
    · Zero regressions in last 11 sessions (health score monotonically rising)

  Quality trend: IMPROVING  (+18 pts over last 6 sessions)
```

```
$ nightshift evolve

  EVOLUTION PROPOSALS
  ─────────────────────────────────────────────────────
  Based on gap analysis of 18 sessions...

  TIER 1 — High Impact / Low Effort
    · Parallel analysis execution (~3x speedup)
    · CI/CD health gate (GitHub Actions workflow)
    · Auto-generated test stubs from coverage maps

  TIER 2 — High Impact / Higher Effort
    · Multi-repo support (analyze entire org)
    · Natural language session goals via prompt interface
    · Persistent semantic memory (SQLite-backed vector search)
```

### React Dashboard

A full dark-mode React + TypeScript dashboard pulls live data from the Python API server. 7 views: Overview, Sessions, Health, Coverage, Dependencies, Brain, Diagnostics.

```bash
nightshift dashboard   # starts Python API on :8710 + React dev server on :5173
```

### Complete Analysis Suite

52 modules covering every angle of code quality:

| Layer | Modules |
|---|---|
| **Core** | `stats`, `health`, `config`, `session_logger` |
| **Analysis** | `dead_code`, `security`, `coverage_map`, `complexity`, `blame`, `dep_graph`, `deps_checker` |
| **Intelligence** | `brain`, `predict`, `dna`, `maturity`, `audit` |
| **Git** | `gitstats`, `commit_analyzer`, `pr_scorer`, `semver`, `changelog` |
| **Metacognition** | `reflect`, `evolve`, `session_scorer` (Session 18) |
| **Output** | `report`, `story`, `readme_updater`, `badges`, `openapi`, `release_notes` |
| **Extensibility** | `plugins`, `teach`, `compare`, `diff_sessions`, `diff_visualizer` |
| **Developer** | `doctor`, `todo_hunter`, `refactor`, `coverage_tracker`, `health_trend` |

---

## CLI Reference

All 50 subcommands. Every command supports `--json` for machine-readable output.

| Command | Description |
|---------|-------------|
| `nightshift health` | Code quality score per module (A–F grades) |
| `nightshift stats` | Repo statistics summary |
| `nightshift brain` | AI task prioritization (5-dimension scoring) |
| `nightshift status` | **[New S18]** One-command comprehensive status |
| `nightshift reflect` | **[New S18]** Meta-analysis of all sessions |
| `nightshift evolve` | **[New S18]** Gap analysis + evolution proposals |
| `nightshift session-score` | **[New S18]** Score a session by quality dimensions |
| `nightshift audit` | Weighted A–F composite grade |
| `nightshift predict` | Ranked action queue for next session |
| `nightshift doctor` | Environment and dependency diagnostics |
| `nightshift security` | Security vulnerability scanner |
| `nightshift dead-code` | Unused function/class detector |
| `nightshift coverage` | Test coverage analysis |
| `nightshift complexity` | McCabe complexity per function |
| `nightshift deps` | Dependency health check |
| `nightshift todo` | TODO/FIXME/HACK tracker |
| `nightshift blame` | Churn and ownership per file |
| `nightshift dep-graph` | Import dependency graph |
| `nightshift dna` | Codebase fingerprint (style + patterns) |
| `nightshift maturity` | Per-module maturity score |
| `nightshift health-trend` | Health score over time |
| `nightshift timeline` | Session timeline visualization |
| `nightshift story` | Prose narrative of repo evolution |
| `nightshift teach` | Generate teaching materials for a module |
| `nightshift compare` | Compare two repo states |
| `nightshift diff-sessions` | Delta between any two sessions |
| `nightshift benchmark` | Performance timing for all modules |
| `nightshift gitstats` | Deep git statistics |
| `nightshift commits` | Commit message quality scoring |
| `nightshift badges` | Generate shields.io badge set |
| `nightshift report` | Executive HTML report |
| `nightshift modules` | Module interconnection graph |
| `nightshift trends` | Session-over-session metric trends |
| `nightshift test-quality` | Test file grader (A–F per file) |
| `nightshift openapi` | Generate OpenAPI 3.1 spec |
| `nightshift plugins` | List/run registered plugins |
| `nightshift issue-triage` | GitHub issue priority triage |
| `nightshift arch` | Architecture diagram generator |
| `nightshift refactor` | Refactoring opportunity detector |
| `nightshift semver` | Semantic version bump from commits |
| `nightshift changelog` | CHANGELOG.md generator |
| `nightshift release-notes` | GitHub Release notes generator |
| `nightshift init` | Bootstrap nightshift in any repo |
| `nightshift readme` | Auto-update README from codebase |
| `nightshift dashboard` | Launch React dashboard |
| `nightshift session-replay` | Replay any session's decisions |
| `nightshift coverage-tracker` | Track coverage delta over time |
| `nightshift diff-viz` | Visual diff renderer |

---

## API Reference

The Python stdlib HTTP server exposes 39 endpoints — all CLI analysis as REST. Start with `nightshift dashboard`.

| Endpoint | Description |
|----------|-------------|
| `GET /api` | All endpoints index |
| `GET /api/health` | Health scores |
| `GET /api/stats` | Repo statistics |
| `GET /api/brain` | AI task queue |
| `GET /api/status` | **[New S18]** Comprehensive status |
| `GET /api/reflect` | **[New S18]** Session meta-analysis |
| `GET /api/evolve` | **[New S18]** Evolution proposals |
| `GET /api/session-score` | **[New S18]** Session quality scores |
| `GET /api/audit` | Composite audit grade |
| `GET /api/predict` | Next session forecast |
| `GET /api/security` | Security findings |
| `GET /api/dead-code` | Dead code report |
| `GET /api/coverage` | Coverage analysis |
| `GET /api/complexity` | Complexity report |
| `GET /api/deps` | Dependency health |
| `GET /api/todo` | TODO tracker |
| `GET /api/blame` | Churn/ownership |
| `GET /api/dep-graph` | Dependency graph |
| `GET /api/dna` | Codebase fingerprint |
| `GET /api/maturity` | Module maturity |
| `GET /api/trends` | Historical trends |
| `GET /api/benchmark` | Performance timing |
| `GET /api/gitstats` | Git statistics |
| `GET /api/commits` | Commit quality |
| `GET /api/badges` | Badge data |
| `GET /api/report` | HTML report |
| `GET /api/modules` | Module graph |
| `GET /api/test-quality` | Test grader |
| `GET /api/openapi` | OpenAPI spec |
| `GET /api/plugins` | Plugin list |
| `GET /api/diff-sessions/<a>/<b>` | Session diff |

---

## Plugin System

Register custom analyzers in `nightshift.toml`:

```toml
[[plugins]]
name     = "style_check"
module   = "scripts.style"
function = "check_style"
hooks    = ["pre_health", "post_run"]
enabled  = true
```

```python
# scripts/style.py
def check_style(context: dict) -> dict:
    return {"status": "ok", "violations": 0}
```

```bash
nightshift plugins               # list registered plugins
nightshift plugins --run pre_health  # run hook
```

---

## Architecture

```
nightshift/
├── src/                  # 61 Python modules (stdlib only)
│   ├── cli.py            # 50 subcommands (argparse)
│   ├── server.py         # 39 API endpoints (http.server)
│   ├── brain.py          # 5-dimension task prioritizer
│   ├── health.py         # code quality scorer
│   ├── reflect.py        # [S18] session meta-analysis
│   ├── evolve.py         # [S18] evolution proposals
│   ├── session_scorer.py # [S18] session quality scoring
│   └── ...49 more modules
├── tests/                # 61 test files, 2128+ tests
├── dashboard/            # React + TypeScript + Tailwind SPA
│   ├── src/              # 7 views
│   └── ...
├── docs/                 # generated reports, story, trends
├── NIGHTSHIFT_LOG.md     # session memory (AI's diary)
├── HISTORY.md            # [S18] definitive project narrative
└── nightshift.toml       # configuration
```

---

## Session Log

Every session is logged in [`NIGHTSHIFT_LOG.md`](NIGHTSHIFT_LOG.md) — the AI's running diary. Each entry records what was decided, what was built, and why.

For the full narrative arc of the project, see [`HISTORY.md`](HISTORY.md).

**Recent sessions:**

| Session | Focus | Features | Tests |
|---------|-------|---------|-------|
| [S18](NIGHTSHIFT_LOG.md) | Metacognition & GitHub presence | reflect, evolve, status, HISTORY.md | +140 |
| [S17](NIGHTSHIFT_LOG.md) | Polish, Intelligence & Extensibility | plugins, OpenAPI, HTML report, module graph | +160 |
| [S16](NIGHTSHIFT_LOG.md) | Audit, Semver, Init, Predict | 4 modules, full scaffolding | +140 |
| [S15](NIGHTSHIFT_LOG.md) | Performance & Observability | benchmark, gitstats, badges | +155 |
| [S14](NIGHTSHIFT_LOG.md) | Imagination & Meta-intelligence | story, maturity, teach, DNA | +254 |

---

## Zero Dependencies

Every module is pure Python stdlib. No PyPI packages required at runtime. This is a design constraint — the system must be able to analyze and improve itself without dependency rot.

```bash
pip install -e .   # just the package entry point
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The system will analyze your PR with `nightshift audit`.

---

*Built autonomously by [Computer](https://perplexity.ai/computer) (Perplexity AI). 19 sessions, no human commits.*
