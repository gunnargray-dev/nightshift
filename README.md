# Nightshift

<!-- badges:start -->
[![Sessions](https://img.shields.io/badge/sessions-21-blueviolet?style=flat-square)](https://github.com/gunnargray-dev/nightshift/blob/main/NIGHTSHIFT_LOG.md)
[![PRs](https://img.shields.io/badge/PRs-46-blue?style=flat-square)](https://github.com/gunnargray-dev/nightshift/pulls)
[![Tests](https://img.shields.io/badge/tests-2128%2B-brightgreen?style=flat-square)](https://github.com/gunnargray-dev/nightshift/tree/main/tests)
[![Modules](https://img.shields.io/badge/modules-61-orange?style=flat-square)](https://github.com/gunnargray-dev/nightshift/tree/main/src)
[![CLI](https://img.shields.io/badge/CLI_commands-50-cyan?style=flat-square)](https://github.com/gunnargray-dev/nightshift/blob/main/src/cli.py)
[![API](https://img.shields.io/badge/API_endpoints-39-teal?style=flat-square)](https://github.com/gunnargray-dev/nightshift/blob/main/src/server.py)
[![Python](https://img.shields.io/badge/python-3.10%2B-yellow?style=flat-square)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-lightgrey?style=flat-square)](LICENSE)
<!-- badges:end -->

> **An AI that improves its own codebase — autonomously, every session.**

Nightshift is a self-improving autonomous development system. An AI runs overnight, analyzes the repo, identifies what matters most, ships features, writes tests, and opens a pull request — all without human input. Then it does it again the next session, learning from what it built.

**21 sessions. 46 PRs. 61 modules. 2,128+ tests. Zero human commits.**

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

  REFLECTION REPORT
  ───────────────────────────────────────────────

  Sessions analyzed: 18
  Total PRs: 41
  Total tests: 2,128

  Top 3 sessions by impact:
    1. Session 5   — Brain + Dashboard       score: 92
    2. Session 12  — Config + Compare        score: 88
    3. Session 15  — Benchmark + API         score: 86

  Biggest improvement arc:
    Early sessions: basic tooling
    Recent sessions: metacognition + scaling

  Next evolution proposal:
    “Nightshift should begin enforcing its own quality gates in CI.”
```

### Dashboard (Session 5)

Nightshift includes a GitHub Pages dashboard showing repo evolution over time.

- **Live dashboard:** https://gunnargray-dev.github.io/nightshift/
- **Source:** `docs/index.html`

### API Surface

Nightshift exposes a lightweight built-in API server for integration and visualization.

```
$ nightshift server

Nightshift API Server running on http://localhost:8765

Endpoints:
  GET /api/status
  GET /api/health
  GET /api/dna
  GET /api/maturity
  GET /api/complexity
  GET /api/coupling
  GET /api/coverage
  GET /api/security
  GET /api/deadcode
  GET /api/blame
  GET /api/gitstats
  GET /api/benchmark
  GET /api/story
  GET /api/reflect
  GET /api/evolve
  GET /api/timeline
  GET /api/deps
  GET /api/export
  GET /api/audit
  GET /api/arch
  GET /api/session
  GET /api/compare
  GET /api/prscore
  GET /api/coveragemap
```

---

## Repository Structure

```
nightshift/
├── src/                 # Nightshift core
├── tests/               # 2,000+ tests (one for each module)
├── docs/                # Generated docs + dashboard
├── dashboard/           # React UI
├── .github/             # CI + templates
└── NIGHTSHIFT_LOG.md    # Memory: every session logged
```

---

## The Experiment

This repo is a real experiment:

- The AI (Computer) runs overnight.
- It reads the repo.
- It picks roadmap tasks.
- It implements them.
- It writes tests.
- It opens PRs.
- It updates the docs.

The goal is to measure whether autonomous code improvement can compound.

---

## Contributing

Want to influence what the AI builds next?

1. Open a GitHub issue describing what you want.
2. The AI will triage and score it.
3. High-priority items will be pulled into the next session.

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

MIT
