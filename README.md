# Awake

<!-- badges:start -->
[![Sessions](https://img.shields.io/badge/sessions-26-blueviolet?style=flat-square)](https://github.com/gunnargray-dev/awake/blob/main/AWAKE_LOG.md)
[![PRs](https://img.shields.io/badge/PRs-57-blue?style=flat-square)](https://github.com/gunnargray-dev/awake/pulls)
[![Tests](https://img.shields.io/badge/tests-2496%2B-brightgreen?style=flat-square)](https://github.com/gunnargray-dev/awake/tree/main/tests)
[![Modules](https://img.shields.io/badge/modules-68-orange?style=flat-square)](https://github.com/gunnargray-dev/awake/tree/main/src)
[![CLI](https://img.shields.io/badge/CLI_commands-55-cyan?style=flat-square)](https://github.com/gunnargray-dev/awake/blob/main/src/cli.py)
[![API](https://img.shields.io/badge/API_endpoints-39-teal?style=flat-square)](https://github.com/gunnargray-dev/awake/blob/main/src/server.py)
[![Python](https://img.shields.io/badge/python-3.10%2B-yellow?style=flat-square)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-lightgrey?style=flat-square)](LICENSE)
<!-- badges:end -->

> **An AI that improves its own codebase -- autonomously, every session.**

Awake is a self-improving autonomous development system. An AI runs overnight, analyzes the repo, identifies what matters most, ships features, writes tests, and opens a pull request -- all without human input. Then it does it again the next session, learning from what it built.

**26 sessions. 57 PRs. 68 modules. 2,496+ tests. Zero human commits.**

---

## How It Works

```
+---------------------------------------------------------------------+
|                        AWAKE PIPELINE                          |
|                                                                     |
|   1. ANALYZE          2. DECIDE           3. BUILD                  |
|   ----------         ----------          -------                    |
|                                                                     |
|   awake stats --> brain.py      --> write code                 |
|   awake health    (5-dimension       write tests               |
|   awake audit     scoring:           update CLI                |
|   awake predict   . complexity       update API                |
|   awake dna       . coverage                                   |
|                        . churn         4. VERIFY                    |
|                        . debt          -------                      |
|                        . momentum)     pytest (all green)           |
|                             |                                       |
|                             v          5. SHIP                      |
|                         ranked task    ------                       |
|                         queue          git commit                   |
|                                        open PR                      |
|                                        update log                   |
+---------------------------------------------------------------------+

  METACOGNITION LAYER (new in Session 18)
  ----------------------------------------
  awake reflect  --> analyzes ALL past sessions, scores quality,
                          identifies patterns, surfaces what the AI
                          learned and how it has improved over time

  awake evolve   --> gap analysis + next evolution proposals
                          based on system's own growth trajectory

  awake status   --> one-command comprehensive health snapshot
```

The system is entirely self-contained. Every module is pure Python stdlib -- no runtime dependencies. The AI reads `AWAKE_LOG.md` as memory, uses `brain.py` as its decision engine, and leaves behind a PR as evidence of its work.

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/gunnargray-dev/awake
cd awake
pip install -e .

# Run a health check
awake health

# See what the AI would do next
awake brain

# View the full status dashboard (new in Session 18)
awake status

# Launch the React dashboard
awake dashboard
# -> http://localhost:5173

# Read the AI's self-analysis
awake reflect

# Ask the AI what it should become
awake evolve

# Auto-generate missing docstrings (new in Session 23)
awake docstrings --dry-run
awake docstrings --apply

# Analyze the AI's own development history (new in Session 24)
awake insights

# Code quality metrics (new in Session 24)
awake complexity
awake coupling
```

---

## Feature Showcase

### Intelligence Core

The brain is a five-dimension scoring engine. Every module in the codebase gets scored against five independent signals, and the results are ranked into a prioritized action queue for the next session.

```
$ awake brain

  BRAIN ANALYSIS -- Session 18 context
  ---------------------------------------------------------

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

The system can now reflect on its own history -- scoring past sessions, identifying productivity patterns, and proposing its own evolution.

Run:

```bash
awake reflect
```

...and it will produce:

- A quality grade for every past session
- A heatmap of productivity patterns
- A ranked list of what improved vs. regressed
- A forecast of what it should build next

### Gap Analysis (Session 18)

Run:

```bash
awake evolve
```

...and it will produce:

- Tier 1 quick wins (easy improvements)
- Tier 2 deeper modules (medium projects)
- Tier 3 explorations (ambitious evolutions)

---

## The Repo's Growth (Visualization)

You can also browse the full project dashboard:

- `docs/index.html` -- interactive evolution dashboard

---

### Session Insights (Session 24)

An AI analyzing the history of its own creation. Run:

```bash
awake insights
```

...and it will tell you things like:

- *Session 5 was the most productive night: 14 PRs in a single session -- 27% of all PRs ever opened.*
- *The AI-to-human contribution ratio shifted from 0% to ~99%: Computer now writes virtually all code.*
- *Computer showed a strong preference for analysis modules: 43% of all tasks are code analysis tools.*
- Velocity trends, streak detection, anomaly identification

---

## Philosophy

Awake is an experiment in recursive improvement.

- AI builds the system
- The system measures itself
- The system proposes changes
- The AI executes those changes

This repo is the artifact.

---

## License

MIT