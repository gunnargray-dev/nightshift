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
| Nights active | 1 |
| Total PRs | 3 |
| Total commits | 4 |
| Lines changed | 700 |

*Stats are updated by Computer each session.*

## Project

Nightshift is a **self-improving autonomous development system**. The repo is both the project and the meta-project — Computer builds tools, then improves the tools it used to build them.

See [`ROADMAP.md`](ROADMAP.md) for what's planned.  
See [`NIGHTSHIFT_LOG.md`](NIGHTSHIFT_LOG.md) for what's happened.  
See [`.github/NIGHTSHIFT_RULES.md`](.github/NIGHTSHIFT_RULES.md) for the constraints.

## For Humans

Want the AI to build something? [Open an issue](../../issues/new) with the label `human-priority` and Computer will address it in the next overnight session.

---

*Built by [@gunnargray-dev](https://github.com/gunnargray-dev) and Perplexity Computer.*
