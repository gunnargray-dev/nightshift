# Awake Live Dashboard Design

## Overview

Replace the static HTML dashboard with a live, real-time dashboard powered by a local Python API server and a React + Vite frontend. Design language inspired by Linear -- dark, flat, minimal, no emojis.

## Architecture

```
awake/
├── src/                    # existing CLI modules (unchanged)
├── src/server.py           # NEW: HTTP API server wrapping CLI commands
├── dashboard/              # NEW: React + Vite SPA
│   ├── src/
│   │   ├── App.tsx
│   │   ├── api/            # fetch hooks for each endpoint
│   │   ├── components/     # shared UI primitives
│   │   ├── views/          # one per sidebar nav item
│   │   └── styles/         # global theme + tailwind config
│   ├── package.json
│   └── vite.config.ts
```

### Backend: `src/server.py`

- stdlib `http.server` + `subprocess` to invoke CLI commands
- CORS headers for local dev
- Zero new runtime dependencies (maintains awake principle)
- Endpoints:
  - `GET /api/health` -- health report with per-file scores
  - `GET /api/stats` -- repo stats (sessions, PRs, commits, lines)
  - `GET /api/coverage` -- coverage history and trends
  - `GET /api/sessions` -- list of all sessions
  - `GET /api/replay/{n}` -- reconstruct session N
  - `GET /api/diff/{n}` -- diff summary for session N
  - `GET /api/depgraph` -- module dependency graph
  - `GET /api/plan` -- brain's current task ranking
  - `GET /api/doctor` -- diagnostic checks
  - `GET /api/todos` -- stale TODO/FIXME annotations
  - `GET /api/triage` -- triaged issues
  - `GET /api/scores` -- PR quality scores
  - `GET /api/changelog` -- changelog entries

### Frontend: React + Vite SPA

- React 18 + TypeScript
- Tailwind CSS for styling
- TanStack Query (React Query) for data fetching + caching
- Lucide React for icons
- React Router for navigation

### CLI Integration

```bash
awake dashboard            # starts API on :8710, opens browser
awake dashboard --port N   # custom API port
```

The `dashboard` subcommand starts the API server, serves built frontend assets (or proxies to Vite dev server), and opens the browser.

## Views

### 1. Overview

- Stat cards: sessions run, total PRs, source modules, test count, coverage %
- Health gauge (overall score)
- Recent session activity feed
- Data: `stats`, `health`, `coverage`

### 2. Sessions

- Vertical timeline of all sessions
- Click to expand: tasks completed, PRs opened, code diff summary, decisions
- Data: `replay/{n}`, `diff/{n}`

### 3. Health

- Per-file health table (sortable by score, name, session added)
- Sparkline trends per file
- Overall health score gauge with delta
- Data: `health`, health trend history

### 4. Coverage

- Coverage % over time line chart
- Per-file coverage table with delta indicators
- Data: `coverage`

### 5. Dependencies

- Module relationship visualization (directed graph or adjacency matrix)
- Fan-in / fan-out stats per module
- Circular dependency warnings
- Data: `depgraph`

### 6. Brain

- Task candidates ranked by composite score
- Breakdown bars for each scoring dimension (urgency, roadmap alignment, health improvement, complexity fit, synergy)
- Issue triage list with priority badges
- Data: `plan`, `triage`

### 7. Diagnostics

- Doctor check results: pass/warn/fail with details
- Stale TODOs table with file, line, age, author
- PR quality grades table
- Data: `doctor`, `todos`, `scores`

## Design System

### Colors

| Token | Value | Usage |
|-------|-------|-------|
| `bg-primary` | `#0a0a0b` | Page background |
| `bg-surface` | `#141415` | Cards, sidebar |
| `bg-elevated` | `#1c1c1e` | Hover states, modals |
| `border` | `#2a2a2d` | All borders (1px, subtle) |
| `text-primary` | `#ededef` | Headings, key data |
| `text-secondary` | `#8a8a8e` | Labels, descriptions |
| `text-tertiary` | `#5c5c60` | Timestamps, meta |
| `accent` | `#6e6afa` | Links, active states, primary actions |
| `success` | `#45d483` | Pass, healthy, positive delta |
| `warning` | `#f0b232` | Warn, caution |
| `error` | `#ef5f5f` | Fail, critical, negative delta |

### Typography

- **UI text:** Inter (400, 500, 600 weights)
- **Code/data:** JetBrains Mono
- No emojis -- use Lucide icons exclusively

### Layout

- Fixed left sidebar: 200px, `bg-surface`, 1px right border
- Sidebar: wordmark at top, nav items with Lucide icons, active state uses `accent` bg at 10% opacity
- Main content: consistent 32px padding, max-width 1280px
- Border radius: max 6px
- No box shadows -- flat surfaces with 1px borders only

### Data Fetching

- TanStack Query with 30-second default poll interval for overview metrics
- Session-specific data fetched on demand (user clicks to load)
- Loading: skeleton shimmer placeholders, no spinners
- Error: inline error message with retry button

## Launch Flow

1. `awake dashboard` command added to CLI
2. Starts Python API server (`src/server.py`) on port 8710
3. In production mode: serves `dashboard/dist/` static files
4. In dev mode: proxies to Vite dev server on port 5173
5. Opens browser to dashboard URL
