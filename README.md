# Nightshift

<!-- badges:start -->
[![Sessions](https://img.shields.io/badge/sessions-22-blueviolet?style=flat-square)](https://github.com/gunnargray-dev/nightshift/blob/main/NIGHTSHIFT_LOG.md)
[![PRs](https://img.shields.io/badge/PRs-47-blue?style=flat-square)](https://github.com/gunnargray-dev/nightshift/pulls)
[![Tests](https://img.shields.io/badge/tests-2128%2B-brightgreen?style=flat-square)](https://github.com/gunnargray-dev/nightshift/tree/main/tests)
[![Modules](https://img.shields.io/badge/modules-61-orange?style=flat-square)](https://github.com/gunnargray-dev/nightshift/tree/main/src)
[![CLI](https://img.shields.io/badge/CLI_commands-50-cyan?style=flat-square)](https://github.com/gunnargray-dev/nightshift/blob/main/src/cli.py)
[![API](https://img.shields.io/badge/API_endpoints-39-teal?style=flat-square)](https://github.com/gunnargray-dev/nightshift/blob/main/src/server.py)
[![Python](https://img.shields.io/badge/python-3.10%2B-yellow?style=flat-square)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-lightgrey?style=flat-square)](LICENSE)
<!-- badges:end -->

> **An AI that improves its own codebase — autonomously, every session.**

Nightshift is a self-improving autonomous development system. An AI runs overnight, analyzes the repo, identifies what matters most, ships features, writes tests, and opens a pull request — all without human input. Then it does it again the next session, learning from what it built.

**22 sessions. 47 PRs. 61 modules. 2,128+ tests. Zero human commits.**

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

Run:

```bash
nightshift reflect
```

...and it will produce:

- A quality grade for every past session
- A heatmap of productivity patterns
- A ranked list of what improved vs. regressed
- A forecast of what it should build next

### Gap Analysis (Session 18)

Run:

```bash
nightshift evolve
```

...and it will produce:

- Tier 1 quick wins (easy improvements)
- Tier 2 deeper modules (medium projects)
- Tier 3 explorations (ambitious evolutions)

---

## The Repo's Growth (Visualization)

You can also browse the full project dashboard:

- `docs/index.html` — interactive evolution dashboard

---

## Philosophy

Nightshift is an experiment in recursive improvement.

- AI builds the system
- The system measures itself
- The system proposes changes
- The AI executes those changes

This repo is the artifact.

---

## License

MIT
