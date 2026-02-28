# Error Recovery Documentation

> How Nightshift handles failures, degrades gracefully, and heals itself.

---

## Overview

Nightshift is designed with a "fail gracefully, never silently" philosophy. Every module is expected to:

1. Return meaningful output even when the environment is incomplete
2. Log what went wrong and why
3. Suggest a remediation action
4. Never crash the entire pipeline due to a single module's failure

---

## Recovery Principles

### 1. Isolation

Each analysis module is independent. If `security.py` fails, `health.py`, `brain.py`, and all other modules continue running. The pipeline reports a partial result rather than aborting.

```
$ nightshift health
  health.py      ✓  82/100
  dead_code.py   ✓  74/100
  security.py    ✗  Error: subprocess timeout (git log took >30s)
  coverage.py    ✓  61/100

  Note: security.py failed — partial score shown
```

### 2. Fallback Data

When a module cannot produce live data (e.g., no git history, no test results), it falls back to cached data from the last successful run:

```python
# Pattern used in health.py, audit.py, predict.py
try:
    result = compute_live()
except Exception as e:
    result = load_cached_result()
    result["_stale"] = True
    result["_error"] = str(e)
```

Cached results are stored in `docs/*.json` and are always preferred over crashing.

### 3. Subprocess Timeouts

All subprocess calls (git, pytest, grep) have a default 30-second timeout. If a subprocess times out:
- The module returns a partial result
- The `_timeout` flag is set in JSON output
- The CLI shows a warning, not an error

```python
# Pattern used in gitstats.py, blame.py, commit_analyzer.py
result = subprocess.run(
    cmd,
    capture_output=True,
    text=True,
    timeout=30,  # always set
    cwd=repo_root,
)
```

### 4. Missing Files

Every module guards against missing source files:

```python
src = Path.cwd() / "src"
if not src.exists():
    return {"error": "src/ directory not found", "score": 0, "grade": "F"}
```

The `nightshift doctor` command validates the entire environment before any analysis.

---

## Common Failure Modes

### Git Not Available

**Symptom:** `gitstats`, `blame`, `commit_analyzer` return empty results.

**Cause:** The `git` executable is not in PATH, or the directory is not a git repo.

**Recovery:**
```bash
# Verify git is available
nightshift doctor

# Initialize git if needed
git init
git add .
git commit -m "Initial commit"

# Re-run analysis
nightshift gitstats
```

### No Test Files

**Symptom:** `coverage`, `test-quality` return "No tests found".

**Cause:** `tests/` directory is empty or doesn't exist.

**Recovery:**
```bash
# Bootstrap the test structure
nightshift init --src

# Check what was created
ls tests/
```

### Health Score Below 60

**Symptom:** `nightshift status` shows RED.

**Cause:** Multiple modules have quality issues accumulating.

**Recovery:**
```bash
# Get prioritized action list
nightshift brain

# Run full diagnostic
nightshift doctor --verbose

# See which modules need attention most
nightshift health --sort score

# Let the AI propose specific fixes
nightshift predict
```

### API Server Won't Start

**Symptom:** `nightshift dashboard` fails; dashboard shows "Connection refused".

**Cause:** Port 8710 already in use, or permissions issue.

**Recovery:**
```bash
# Check what's on port 8710
lsof -i :8710

# Use an alternate port
nightshift dashboard --port 8711

# Or kill the existing process
kill $(lsof -t -i:8710)
nightshift dashboard
```

### Plugin Fails to Load

**Symptom:** `nightshift plugins` shows ERROR for a registered plugin.

**Cause:** Plugin module not found on PYTHONPATH, or function signature mismatch.

**Recovery:**
```bash
# Validate all plugins
nightshift plugins --validate

# Run a specific plugin in debug mode
nightshift plugins --run pre_health --debug

# Disable the failing plugin in nightshift.toml
# Set enabled = false
```

### Large Repo Performance

**Symptom:** Analysis takes >60 seconds.

**Cause:** Large git history or many source files.

**Recovery:**
```bash
# Use the benchmark to identify slow modules
nightshift benchmark

# Limit analysis to recent history
nightshift gitstats --max-commits 100

# Skip slow modules
nightshift health --skip blame,gitstats
```

---

## Self-Healing Mechanisms

### Health Trend Monitoring

`health_trend.py` tracks the health score session-over-session. If the trend is declining:
```
$ nightshift health-trend
  S15: 78  S16: 80  S17: 83  S18: 81  ← minor decline

  Warning: Score declined 2 pts since last session.
  Recommendation: Run 'nightshift predict' to identify root cause.
```

### Predict as Early Warning

`predict.py` uses five signals to identify modules at risk before they fail:

| Signal | What It Catches |
|--------|----------------|
| Module age | Files not touched in many sessions — may accumulate drift |
| Coverage weakness | Undertested modules likely to have hidden bugs |
| Complexity drift | Modules growing more complex without cleanup |
| TODO debt | Unresolved markers that indicate incomplete work |
| Health trend | Modules whose score has been declining |

Run `nightshift predict` before each session to get ahead of issues.

### Audit as Final Gate

`nightshift audit` produces a composite A–F grade combining health (25%), security (25%), dead code (20%), coverage (20%), and complexity (10%). This can be used as a merge gate:

```yaml
# .github/workflows/nightshift.yml
- name: Nightshift audit gate
  run: |
    grade=$(nightshift audit --json | jq -r .grade)
    if [ "$grade" == "D" ] || [ "$grade" == "F" ]; then
      echo "Quality gate failed: $grade"
      exit 1
    fi
```

---

## Recovery Runbook

When something goes wrong, follow this sequence:

```
1. nightshift doctor           → validate environment
2. nightshift status           → see overall state
3. nightshift health           → identify which modules have issues
4. nightshift predict          → get prioritized fix list
5. nightshift brain            → let the AI decide what to fix first
6. [fix the issue]
7. nightshift audit            → verify the fix improved the grade
8. nightshift status           → confirm GREEN
```

---

## Data Preservation

Nightshift never deletes data. All runs produce additive records:

- `NIGHTSHIFT_LOG.md` — append-only session log
- `docs/*.json` — cached analysis results (overwritten per session, not deleted)
- `docs/benchmark_history.json` — rolling history of last 20 benchmark runs
- `docs/health_trend.json` — health score history

To reset all cached data:
```bash
rm docs/*.json
nightshift health --no-cache  # rebuilds from source
```

---

## Getting Help

```bash
nightshift doctor --verbose     # detailed environment check
nightshift health --debug       # verbose health scoring
nightshift --help               # full CLI reference
```

*This document is maintained by the AI. Run `nightshift reflect` to see how error patterns have evolved over sessions.*
