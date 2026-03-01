# Awake Rules

These constraints govern Computer's autonomous behavior during overnight sessions.

## Core Rules

1. **One session per night** — Run once at the scheduled time, submit PRs, then stop.
2. **No force pushes** — Always branch from `main`, never rewrite history.
3. **Every PR must explain itself** — Include: what changed, why, how it works, and test results.
4. **Self-test requirement** — If adding a feature, add or update tests. Run tests before pushing.
5. **Roadmap-driven** — Pick tasks from `ROADMAP.md`. Update the roadmap at end of session.
6. **Log everything** — Append a structured session summary to `AWAKE_LOG.md`.
7. **No breaking changes without migration** — If refactoring, ensure backward compatibility.
8. **Human override** — Issues labeled `human-priority` get addressed first.
9. **Code must run** — All pushed code must be tested locally before being committed.
10. **Atomic PRs** — One feature or fix per PR. No mega-PRs combining unrelated changes.

## Session Structure

```
1. Read repo state (files, issues, PRs, roadmap)
2. Check for human-priority issues
3. Pick 2-5 tasks from roadmap
4. For each task:
   a. Create feature branch from main
   b. Write code locally
   c. Run code and tests
   d. Fix any failures
   e. Push to branch
   f. Open PR with full description
5. Update ROADMAP.md (check off completed, add new ideas)
6. Append session entry to AWAKE_LOG.md
7. Update README.md stats
```

## Commit Message Format

```
[awake] <type>: <short description>

<body explaining what and why>

Session: <session number>
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `ci`, `meta`
