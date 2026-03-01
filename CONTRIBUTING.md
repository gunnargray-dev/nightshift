# Contributing to Awake

Awake is an **autonomous AI development system** — most of the code is written by [Perplexity Computer](https://perplexity.ai) during overnight sessions. But humans are welcome too.

---

## How This Repo Works

Every night, the AI:

1. Reads this repo's full state (code, issues, roadmap, logs)
2. Picks the highest-priority tasks to work on
3. Writes code, runs tests, and opens pull requests
4. Updates `AWAKE_LOG.md` and `ROADMAP.md`

The human maintainer reviews and merges PRs each morning.

---

## How to Request Features or Report Bugs

**The best way to influence what Computer builds next is to open an issue.**

### Opening an Issue for the AI

1. Go to [Issues → New Issue](../../issues/new)
2. Give it a clear title: `[request] Short description of what you want`
3. In the body, explain:
   - **What** you want built or fixed
   - **Why** it matters
   - **Any constraints** (must use stdlib only, must not break existing tests, etc.)
4. Add the label **`human-priority`** — Computer checks for this label first each session

Computer reads every open issue at the start of each session and factors them into its task selection via `src/brain.py`.

### Issue Labels

| Label | Meaning |
|-------|----------|
| `human-priority` | Highest priority — Computer addresses these first |
| `bug` | Something is broken |
| `enhancement` | New feature or improvement |
| `question` | Question about how the system works |
| `good first issue` | Good starting point for human contributors |
| `triage:high` | Auto-assigned by issue triage system — urgent |
| `triage:medium` | Auto-assigned — normal priority |
| `triage:low` | Auto-assigned — low urgency |

---

## Contributing Code (for Humans)

We welcome human contributors! Here's the process:

### Setup

```bash
git clone https://github.com/gunnargray-dev/awake.git
cd awake
pip install -e ".[dev]"
```

### Running Tests

```bash
pytest tests/ -v
# or with coverage:
pytest tests/ --cov=src --cov-report=term-missing
```

### Running the CLI

```bash
awake health          # code health score
awake stats           # repo stats
awake run --session 5 # full end-of-session pipeline
```

### Branch Naming

- Human PRs: `human/<your-username>/<short-description>`
- AI PRs: `awake/session-N-<feature-name>` (auto-generated)

### Pull Request Guidelines

1. All PRs must pass the CI suite (Python 3.10, 3.11, 3.12)
2. New modules must include tests in `tests/test_<module>.py`
3. Follow the existing code style: type hints, docstrings on all public functions
4. No new runtime dependencies without discussion (the zero-dependencies-at-runtime principle has held since Session 1)
5. Fill in the PR template (What / Why / How / Test Results)

### Code Style

- Python 3.10+ with type hints
- Docstrings on all public functions and classes (Computer's health checker will flag missing ones)
- Max line length: 88 characters
- No external runtime dependencies — stdlib + `pytest` for tests only

---

## Talking to the AI

Want to give Computer feedback on a specific PR? Leave a comment on the PR — Computer reads PR comments at the start of each session and may address them in subsequent work.

Want to ask a general question? Open an issue with the `question` label.

---

## Code of Conduct

Be excellent to each other. This is a research project about AI autonomy, and it works best as an open, curious collaboration.

---

*This file was written by Computer during Session 5.*
