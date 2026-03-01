# Live Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a real-time dashboard for awake with a Python API server and React + Vite frontend styled like Linear.

**Architecture:** Two-process model — `src/server.py` wraps all CLI `--json` outputs as HTTP endpoints; `dashboard/` is a React SPA that fetches from those endpoints. The `awake dashboard` CLI command launches both.

**Tech Stack:** Python stdlib `http.server` (backend), React 18 + TypeScript + Vite + Tailwind CSS + TanStack Query + React Router + Lucide React (frontend).

---

### Task 1: API Server — Core HTTP Handler

**Files:**
- Create: `src/server.py`
- Create: `tests/test_server.py`

**Step 1: Write failing test for server request handler**

```python
"""Tests for src/server.py — the Awake dashboard API server."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from http.server import HTTPServer
from io import BytesIO

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.server import AwakeHandler


class MockRequest:
    """Minimal mock for an HTTP request."""

    def __init__(self, path: str):
        self.path = path

    def makefile(self, *args, **kwargs):
        return BytesIO()


def make_handler(path: str) -> AwakeHandler:
    """Create a handler with a mocked request for the given path."""
    handler = AwakeHandler.__new__(AwakeHandler)
    handler.path = path
    handler.headers = {}
    handler.command = "GET"
    handler.request_version = "HTTP/1.1"
    handler._headers_buffer = []
    handler.wfile = BytesIO()
    handler.requestline = f"GET {path} HTTP/1.1"
    handler.client_address = ("127.0.0.1", 0)
    handler.server = MagicMock()
    handler.server.repo_path = Path(".")
    return handler


class TestRouteMatching:
    """Tests that the handler routes to the correct CLI commands."""

    def test_unknown_route_returns_404(self):
        handler = make_handler("/api/unknown")
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.do_GET()
        handler.send_response.assert_called_with(404)

    def test_api_health_route_exists(self):
        handler = make_handler("/api/health")
        with patch.object(handler, '_run_command', return_value='{"score": 90}') as mock_run:
            handler.send_response = MagicMock()
            handler.send_header = MagicMock()
            handler.end_headers = MagicMock()
            handler.do_GET()
            mock_run.assert_called_once()
            handler.send_response.assert_called_with(200)

    def test_api_stats_route_exists(self):
        handler = make_handler("/api/stats")
        with patch.object(handler, '_run_command', return_value='{"nights": 10}') as mock_run:
            handler.send_response = MagicMock()
            handler.send_header = MagicMock()
            handler.end_headers = MagicMock()
            handler.do_GET()
            mock_run.assert_called_once()
            handler.send_response.assert_called_with(200)

    def test_cors_headers_present(self):
        handler = make_handler("/api/stats")
        headers_sent = {}
        def mock_send_header(key, val):
            headers_sent[key] = val
        with patch.object(handler, '_run_command', return_value='{}'):
            handler.send_response = MagicMock()
            handler.send_header = mock_send_header
            handler.end_headers = MagicMock()
            handler.do_GET()
        assert "Access-Control-Allow-Origin" in headers_sent
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/gunnar/Documents/Dev/awake && python -m pytest tests/test_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.server'`

**Step 3: Write the server implementation**

```python
"""HTTP API server for the Awake dashboard.

Wraps CLI commands as JSON HTTP endpoints.  Uses only stdlib
(http.server + subprocess) to maintain the zero-dependency principle.

Endpoints
---------
GET /api/health          — Code health report
GET /api/stats           — Repository statistics
GET /api/coverage        — Test coverage trend
GET /api/changelog       — Changelog entries
GET /api/scores          — PR quality scores
GET /api/depgraph        — Module dependency graph
GET /api/doctor          — Repo diagnostics
GET /api/todos           — Stale TODO annotations
GET /api/triage          — Issue triage
GET /api/plan            — Brain task ranking
GET /api/sessions        — List available sessions
GET /api/replay/<n>      — Replay session N
GET /api/diff/<n>        — Diff for session N
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional


ROUTE_MAP: dict[str, list[str]] = {
    "/api/health": ["health", "--json"],
    "/api/stats": ["stats", "--json"],
    "/api/coverage": ["coverage", "--json"],
    "/api/changelog": ["changelog", "--json"],
    "/api/scores": ["score", "--json"],
    "/api/depgraph": ["depgraph", "--json"],
    "/api/doctor": ["doctor", "--json"],
    "/api/todos": ["todos", "--json"],
    "/api/triage": ["triage", "--json"],
    "/api/plan": ["plan", "--json"],
}

PARAMETERIZED_ROUTES: dict[str, tuple[str, list[str]]] = {
    r"/api/replay/(\d+)": ("replay", ["--json", "--session"]),
    r"/api/diff/(\d+)": ("diff", ["--json", "--session"]),
}


class AwakeHandler(BaseHTTPRequestHandler):
    """HTTP request handler that dispatches to awake CLI commands."""

    def _run_command(self, cli_args: list[str]) -> str:
        """Run a awake CLI command and return stdout."""
        repo = getattr(self.server, "repo_path", Path("."))
        result = subprocess.run(
            [sys.executable, "-m", "src.cli"] + cli_args,
            capture_output=True,
            text=True,
            cwd=str(repo),
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or "Command failed")
        return result.stdout

    def _send_json(self, code: int, body: str) -> None:
        """Send a JSON response with CORS headers."""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests."""
        self._send_json(200, "{}")

    def do_GET(self) -> None:
        """Route GET requests to the appropriate CLI command."""
        path = self.path.split("?")[0]  # strip query params

        # Static exact routes
        if path in ROUTE_MAP:
            try:
                result = self._run_command(ROUTE_MAP[path])
                self._send_json(200, result)
            except Exception as e:
                self._send_json(500, json.dumps({"error": str(e)}))
            return

        # Parameterized routes
        for pattern, (cmd, extra_args) in PARAMETERIZED_ROUTES.items():
            m = re.fullmatch(pattern, path)
            if m:
                session_n = m.group(1)
                try:
                    result = self._run_command([cmd] + extra_args + [session_n])
                    self._send_json(200, result)
                except Exception as e:
                    self._send_json(500, json.dumps({"error": str(e)}))
                return

        # 404
        self._send_json(404, json.dumps({"error": f"Unknown route: {path}"}))

    def log_message(self, fmt: str, *args: object) -> None:  # type: ignore[override]
        """Suppress default request logging (noisy in CLI context)."""


def start_server(
    port: int = 8710,
    repo_path: Optional[Path] = None,
    open_browser: bool = True,
) -> None:
    """Start the Awake API server."""
    if repo_path is None:
        repo_path = Path.cwd()
    server = HTTPServer(("localhost", port), AwakeHandler)
    server.repo_path = repo_path  # type: ignore[attr-defined]
    url = f"http://localhost:{port}"
    print(f"Awake dashboard API running at {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/gunnar/Documents/Dev/awake && python -m pytest tests/test_server.py -v`
Expected: All 4 tests PASS

---

### Task 2: Register `dashboard` CLI Subcommand

**Files:**
- Modify: `src/cli.py`

**Step 1: Write failing test for new CLI subcommand**

```python
# Add to tests/test_cli.py

def test_dashboard_subcommand_exists():
    """Verify the dashboard subcommand is registered."""
    result = subprocess.run(
        [sys.executable, "-m", "src.cli", "dashboard", "--help"],
        capture_output=True, text=True, cwd=str(REPO_ROOT)
    )
    assert result.returncode == 0
    assert "port" in result.stdout.lower()
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/gunnar/Documents/Dev/awake && python -m pytest tests/test_cli.py::test_dashboard_subcommand_exists -v`
Expected: FAIL

**Step 3: Add dashboard subcommand to cli.py**

Find the subcommand registration section in `src/cli.py` and add:

```python
# dashboard
parser_dashboard = subparsers.add_parser(
    "dashboard",
    help="Launch the live repo evolution dashboard",
)
parser_dashboard.add_argument(
    "--port",
    type=int,
    default=8710,
    help="Port for the API server (default: 8710)",
)
parser_dashboard.add_argument(
    "--no-browser",
    action="store_true",
    help="Don't open the browser automatically",
)
```

And in the dispatch section:

```python
elif args.command == "dashboard":
    from src.server import start_server
    start_server(
        port=args.port,
        repo_path=Path.cwd(),
        open_browser=not args.no_browser,
    )
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/gunnar/Documents/Dev/awake && python -m pytest tests/test_cli.py::test_dashboard_subcommand_exists -v`
Expected: PASS

---

### Task 3: Scaffold React + Vite Frontend

**Files:**
- Create: `dashboard/package.json`
- Create: `dashboard/vite.config.ts`
- Create: `dashboard/tsconfig.json`
- Create: `dashboard/index.html`
- Create: `dashboard/tailwind.config.js`
- Create: `dashboard/postcss.config.js`

**Step 1: Create `dashboard/package.json`**

```json
{
  "name": "awake-dashboard",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.0.0",
    "lucide-react": "^0.344.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.22.0"
  },
  "devDependencies": {
    "@types/react": "^18.2.0",
    "@types/react-dom": "^18.2.0",
    "@vitejs/plugin-react": "^4.2.0",
    "autoprefixer": "^10.4.17",
    "postcss": "^8.4.35",
    "tailwindcss": "^3.4.1",
    "typescript": "^5.3.3",
    "vite": "^5.1.0"
  }
}
```

**Step 2: Create `dashboard/vite.config.ts`**

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8710',
    },
  },
  build: {
    outDir: '../docs/dashboard',
    emptyOutDir: true,
  },
});
```

**Step 3: Create `dashboard/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"]
}
```

**Step 4: Create `dashboard/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Awake Dashboard</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

**Step 5: Create `dashboard/tailwind.config.js`**

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'bg-primary': '#0a0a0b',
        'bg-surface': '#141415',
        'bg-elevated': '#1c1c1e',
        border: '#2a2a2d',
        'text-primary': '#ededef',
        'text-secondary': '#8a8a8e',
        'text-tertiary': '#5c5c60',
        accent: '#6e6afa',
        success: '#45d483',
        warning: '#f0b232',
        error: '#ef5f5f',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      borderRadius: {
        DEFAULT: '4px',
        md: '6px',
      },
    },
  },
  plugins: [],
};
```

**Step 6: Create `dashboard/postcss.config.js`**

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

**Step 7: Verify node + npm available**

Run: `node --version && npm --version`
Expected: Both print version strings (no error)

**Step 8: Install dependencies**

Run: `cd /Users/gunnar/Documents/Dev/awake/dashboard && npm install`
Expected: `node_modules/` directory created, no errors

---

### Task 4: Sidebar Component + Layout Shell

**Files:**
- Create: `dashboard/src/main.tsx`
- Create: `dashboard/src/styles/globals.css`
- Create: `dashboard/src/components/Sidebar.tsx`
- Create: `dashboard/src/App.tsx` (initial shell)

**Step 1: Create `dashboard/src/styles/globals.css`**

```css
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  background-color: #0a0a0b;
  color: #ededef;
  font-family: 'Inter', system-ui, sans-serif;
  -webkit-font-smoothing: antialiased;
}

/* Remove default focus outline, replace with subtle ring */
*:focus-visible {
  outline: 2px solid #6e6afa;
  outline-offset: 2px;
}
```

**Step 2: Create `dashboard/src/main.tsx`**

```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import './styles/globals.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
```

**Step 3: Create `dashboard/src/components/Sidebar.tsx`**

```tsx
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  History,
  Heart,
  TestTube2,
  Network,
  Brain,
  Stethoscope,
} from 'lucide-react';

const NAV = [
  { to: '/', icon: LayoutDashboard, label: 'Overview' },
  { to: '/sessions', icon: History, label: 'Sessions' },
  { to: '/health', icon: Heart, label: 'Health' },
  { to: '/coverage', icon: TestTube2, label: 'Coverage' },
  { to: '/deps', icon: Network, label: 'Dependencies' },
  { to: '/brain', icon: Brain, label: 'Brain' },
  { to: '/diagnostics', icon: Stethoscope, label: 'Diagnostics' },
];

export function Sidebar() {
  return (
    <aside className="fixed inset-y-0 left-0 w-[200px] bg-bg-surface border-r border-border flex flex-col">
      <div className="px-4 py-5 border-b border-border">
        <span className="text-sm font-semibold text-text-primary tracking-tight">Awake</span>
        <span className="ml-1.5 text-xs text-text-tertiary">dashboard</span>
      </div>
      <nav className="flex-1 px-2 py-3 space-y-0.5">
        {NAV.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-2.5 px-3 py-2 rounded text-sm transition-colors ${
                isActive
                  ? 'bg-accent/10 text-accent font-medium'
                  : 'text-text-secondary hover:text-text-primary hover:bg-bg-elevated'
              }`
            }
          >
            <Icon size={15} strokeWidth={1.75} />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="px-4 py-3 border-t border-border">
        <p className="text-xs text-text-tertiary">autonomous dev system</p>
      </div>
    </aside>
  );
}
```

**Step 4: Create `dashboard/src/App.tsx` (shell)**

```tsx
import { Routes, Route } from 'react-router-dom';
import { Sidebar } from './components/Sidebar';

function Placeholder({ name }: { name: string }) {
  return (
    <div className="p-8">
      <h1 className="text-xl font-semibold text-text-primary">{name}</h1>
      <p className="mt-2 text-text-secondary">Loading…</p>
    </div>
  );
}

export default function App() {
  return (
    <div className="flex min-h-screen bg-bg-primary">
      <Sidebar />
      <main className="ml-[200px] flex-1">
        <Routes>
          <Route path="/" element={<Placeholder name="Overview" />} />
          <Route path="/sessions" element={<Placeholder name="Sessions" />} />
          <Route path="/health" element={<Placeholder name="Health" />} />
          <Route path="/coverage" element={<Placeholder name="Coverage" />} />
          <Route path="/deps" element={<Placeholder name="Dependencies" />} />
          <Route path="/brain" element={<Placeholder name="Brain" />} />
          <Route path="/diagnostics" element={<Placeholder name="Diagnostics" />} />
        </Routes>
      </main>
    </div>
  );
}
```

**Step 5: Verify dev server starts**

Run: `cd /Users/gunnar/Documents/Dev/awake/dashboard && npm run dev -- --port 5173`
Expected: Vite starts, no TypeScript or import errors
Stop with Ctrl+C after confirming it starts.

---

### Task 5: API Fetch Hooks

**Files:**
- Create: `dashboard/src/api/index.ts`

**Step 1: Create `dashboard/src/api/index.ts`**

```typescript
import { useQuery } from '@tanstack/react-query';

const BASE = '/api';

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

// Health
export interface FileHealth {
  file: string;
  score: number;
  grade: string;
  issues: string[];
}
export interface HealthReport {
  overall_score: number;
  grade: string;
  files: FileHealth[];
  generated_at: string;
}
export const useHealth = () =>
  useQuery({ queryKey: ['health'], queryFn: () => get<HealthReport>('/health'), refetchInterval: 30_000 });

// Stats
export interface RepoStats {
  nights_run: number;
  total_prs: number;
  source_modules: number;
  test_count: number;
  total_commits: number;
  lines_changed: number;
}
export const useStats = () =>
  useQuery({ queryKey: ['stats'], queryFn: () => get<RepoStats>('/stats'), refetchInterval: 30_000 });

// Coverage
export interface CoverageRun {
  session: number;
  date: string;
  coverage_pct: number;
}
export interface CoverageReport {
  current_pct: number;
  trend: CoverageRun[];
}
export const useCoverage = () =>
  useQuery({ queryKey: ['coverage'], queryFn: () => get<CoverageReport>('/coverage'), refetchInterval: 60_000 });

// Sessions
export interface SessionMeta {
  session: number;
  date: string;
  prs: number;
  theme: string;
}
export const useSessions = () =>
  useQuery({ queryKey: ['sessions'], queryFn: () => get<SessionMeta[]>('/sessions') });

// Session replay
export interface SessionReplay {
  session: number;
  tasks: string[];
  prs: Array<{ number: number; title: string; url: string }>;
  summary: string;
}
export const useReplay = (n: number) =>
  useQuery({ queryKey: ['replay', n], queryFn: () => get<SessionReplay>(`/replay/${n}`), enabled: n >= 0 });

// Diff
export interface DiffReport {
  session: number;
  files_changed: number;
  lines_added: number;
  lines_removed: number;
  by_file: Array<{ file: string; added: number; removed: number }>;
}
export const useDiff = (n: number) =>
  useQuery({ queryKey: ['diff', n], queryFn: () => get<DiffReport>(`/diff/${n}`), enabled: n >= 0 });

// Dep graph
export interface DepGraph {
  nodes: string[];
  edges: Array<[string, string]>;
  fan_in: Record<string, number>;
  fan_out: Record<string, number>;
  cycles: string[][];
}
export const useDepGraph = () =>
  useQuery({ queryKey: ['depgraph'], queryFn: () => get<DepGraph>('/depgraph') });

// Plan (brain)
export interface Task {
  rank: number;
  action: string;
  score: number;
  urgency: number;
  roadmap: number;
  health: number;
  complexity: number;
  synergy: number;
}
export const usePlan = () =>
  useQuery({ queryKey: ['plan'], queryFn: () => get<{ tasks: Task[] }>('/plan'), refetchInterval: 60_000 });

// Doctor
export interface DoctorCheck {
  name: string;
  status: 'pass' | 'warn' | 'fail';
  detail: string;
}
export const useDoctor = () =>
  useQuery({ queryKey: ['doctor'], queryFn: () => get<{ checks: DoctorCheck[] }>('/doctor') });

// TODOs
export interface TodoItem {
  file: string;
  line: number;
  text: string;
  age_days: number;
  author: string;
}
export const useTodos = () =>
  useQuery({ queryKey: ['todos'], queryFn: () => get<{ todos: TodoItem[] }>('/todos') });

// Triage
export interface Issue {
  number: number;
  title: string;
  priority: 'high' | 'medium' | 'low';
  labels: string[];
  url: string;
}
export const useTriage = () =>
  useQuery({ queryKey: ['triage'], queryFn: () => get<{ issues: Issue[] }>('/triage') });

// Scores
export interface PRScore {
  pr: number;
  title: string;
  grade: string;
  score: number;
  dimensions: Record<string, number>;
}
export const useScores = () =>
  useQuery({ queryKey: ['scores'], queryFn: () => get<{ prs: PRScore[] }>('/scores') });
```

---

### Task 6: Shared UI Primitives

**Files:**
- Create: `dashboard/src/components/StatCard.tsx`
- Create: `dashboard/src/components/GradeChip.tsx`
- Create: `dashboard/src/components/SkeletonBlock.tsx`
- Create: `dashboard/src/components/ErrorMessage.tsx`
- Create: `dashboard/src/components/SectionHeader.tsx`

**Step 1: Create `dashboard/src/components/StatCard.tsx`**

```tsx
interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  color?: 'accent' | 'success' | 'warning' | 'error' | 'default';
}

const COLOR_MAP = {
  accent: 'text-accent',
  success: 'text-success',
  warning: 'text-warning',
  error: 'text-error',
  default: 'text-text-primary',
};

export function StatCard({ label, value, sub, color = 'accent' }: StatCardProps) {
  return (
    <div className="bg-bg-surface border border-border rounded-md p-5">
      <div className="text-[11px] font-medium text-text-tertiary uppercase tracking-widest">{label}</div>
      <div className={`text-3xl font-bold mt-1 ${COLOR_MAP[color]}`}>{value}</div>
      {sub && <div className="text-xs text-text-tertiary mt-0.5">{sub}</div>}
    </div>
  );
}
```

**Step 2: Create `dashboard/src/components/GradeChip.tsx`**

```tsx
const GRADE_COLORS: Record<string, string> = {
  'A+': 'bg-success/20 text-success',
  A: 'bg-success/20 text-success',
  'A-': 'bg-success/15 text-success',
  'B+': 'bg-success/10 text-success',
  B: 'bg-success/10 text-success',
  'B-': 'bg-warning/15 text-warning',
  'C+': 'bg-warning/20 text-warning',
  C: 'bg-warning/20 text-warning',
  D: 'bg-error/15 text-error',
  F: 'bg-error/20 text-error',
};

export function GradeChip({ grade }: { grade: string }) {
  const cls = GRADE_COLORS[grade] ?? 'bg-bg-elevated text-text-secondary';
  return (
    <span className={`inline-block text-xs font-bold px-1.5 py-0.5 rounded ${cls}`}>
      {grade}
    </span>
  );
}
```

**Step 3: Create `dashboard/src/components/SkeletonBlock.tsx`**

```tsx
export function SkeletonBlock({ className = '' }: { className?: string }) {
  return (
    <div
      className={`bg-bg-elevated animate-pulse rounded ${className}`}
      aria-hidden
    />
  );
}
```

**Step 4: Create `dashboard/src/components/ErrorMessage.tsx`**

```tsx
import { AlertCircle } from 'lucide-react';

export function ErrorMessage({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 p-4 bg-error/10 border border-error/30 rounded-md">
      <AlertCircle size={16} className="text-error mt-0.5 flex-shrink-0" />
      <div className="flex-1">
        <p className="text-sm text-error">{message}</p>
        {onRetry && (
          <button
            onClick={onRetry}
            className="mt-2 text-xs text-text-secondary hover:text-text-primary underline"
          >
            Retry
          </button>
        )}
      </div>
    </div>
  );
}
```

**Step 5: Create `dashboard/src/components/SectionHeader.tsx`**

```tsx
export function SectionHeader({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="mb-6">
      <h1 className="text-lg font-semibold text-text-primary">{title}</h1>
      {sub && <p className="text-sm text-text-secondary mt-0.5">{sub}</p>}
    </div>
  );
}
```

---

### Task 7: Overview View

**Files:**
- Create: `dashboard/src/views/Overview.tsx`

**Create `dashboard/src/views/Overview.tsx`:**

```tsx
import { useHealth, useStats, useCoverage } from '../api';
import { StatCard } from '../components/StatCard';
import { GradeChip } from '../components/GradeChip';
import { SkeletonBlock } from '../components/SkeletonBlock';
import { ErrorMessage } from '../components/ErrorMessage';
import { SectionHeader } from '../components/SectionHeader';

export function Overview() {
  const health = useHealth();
  const stats = useStats();
  const coverage = useCoverage();

  const isLoading = health.isLoading || stats.isLoading;
  const error = health.error || stats.error;

  return (
    <div className="p-8 max-w-[1280px]">
      <SectionHeader
        title="Overview"
        sub="Live snapshot of autonomous repo evolution"
      />

      {error && (
        <ErrorMessage
          message={error instanceof Error ? error.message : 'Failed to load data'}
          onRetry={() => { health.refetch(); stats.refetch(); }}
        />
      )}

      {/* Stat row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 mb-8">
        {isLoading ? (
          Array.from({ length: 5 }).map((_, i) => (
            <SkeletonBlock key={i} className="h-[88px]" />
          ))
        ) : (
          <>
            <StatCard label="Sessions" value={stats.data?.nights_run ?? '—'} sub="Nights active" />
            <StatCard label="Total PRs" value={stats.data?.total_prs ?? '—'} sub="Merged" color="success" />
            <StatCard label="Modules" value={stats.data?.source_modules ?? '—'} sub="in src/" color="default" />
            <StatCard label="Tests" value={stats.data?.test_count ?? '—'} sub="pytest" color="warning" />
            <StatCard
              label="Coverage"
              value={coverage.data ? `${coverage.data.current_pct}%` : '—'}
              sub="all files"
              color="success"
            />
          </>
        )}
      </div>

      {/* Health summary */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-bg-surface border border-border rounded-md overflow-hidden">
          <div className="px-4 py-3 border-b border-border">
            <span className="text-xs font-semibold text-text-tertiary uppercase tracking-wider">Health Score</span>
          </div>
          <div className="p-6 flex items-center gap-6">
            {health.isLoading ? (
              <SkeletonBlock className="h-20 w-full" />
            ) : (
              <>
                <div>
                  <div className="text-5xl font-bold text-text-primary">
                    {health.data?.overall_score ?? '—'}
                  </div>
                  <div className="text-sm text-text-secondary mt-1">out of 100</div>
                </div>
                <div>
                  <GradeChip grade={health.data?.grade ?? 'N/A'} />
                </div>
              </>
            )}
          </div>
        </div>

        <div className="bg-bg-surface border border-border rounded-md overflow-hidden">
          <div className="px-4 py-3 border-b border-border">
            <span className="text-xs font-semibold text-text-tertiary uppercase tracking-wider">Module Health</span>
          </div>
          <div className="overflow-auto max-h-[240px]">
            {health.isLoading ? (
              <div className="p-4"><SkeletonBlock className="h-40 w-full" /></div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left">
                    <th className="px-4 py-2.5 text-[11px] font-medium text-text-tertiary uppercase tracking-wider border-b border-border">File</th>
                    <th className="px-4 py-2.5 text-[11px] font-medium text-text-tertiary uppercase tracking-wider border-b border-border">Score</th>
                    <th className="px-4 py-2.5 text-[11px] font-medium text-text-tertiary uppercase tracking-wider border-b border-border">Grade</th>
                  </tr>
                </thead>
                <tbody>
                  {(health.data?.files ?? []).map((f) => (
                    <tr key={f.file} className="border-b border-border last:border-0">
                      <td className="px-4 py-2.5 font-mono text-xs text-text-secondary">{f.file}</td>
                      <td className="px-4 py-2.5 text-text-primary">{f.score}</td>
                      <td className="px-4 py-2.5"><GradeChip grade={f.grade} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
```

---

### Task 8: Sessions View

**Files:**
- Create: `dashboard/src/views/Sessions.tsx`

```tsx
import { useState } from 'react';
import { useSessions, useReplay, useDiff } from '../api';
import { SectionHeader } from '../components/SectionHeader';
import { SkeletonBlock } from '../components/SkeletonBlock';
import { ChevronDown, ChevronRight } from 'lucide-react';

function SessionRow({ session }: { session: number; date: string; prs: number; theme: string }) {
  const [expanded, setExpanded] = useState(false);
  const replay = useReplay(expanded ? session : -1);
  const diff = useDiff(expanded ? session : -1);

  return (
    <div className="border-b border-border last:border-0">
      <button
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-bg-elevated text-left"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span className="bg-bg-elevated border border-border rounded-full px-2.5 py-0.5 text-xs font-bold text-accent">S{session}</span>
        <span className="flex-1 text-sm text-text-primary">{theme || `Session ${session}`}</span>
        <span className="text-xs text-text-tertiary">{prs} PR{prs !== 1 ? 's' : ''}</span>
        <span className="text-xs text-text-tertiary ml-4">{date}</span>
      </button>
      {expanded && (
        <div className="px-10 pb-4">
          {replay.isLoading ? <SkeletonBlock className="h-20 w-full" /> : (
            <div className="space-y-3">
              <div>
                <p className="text-xs font-medium text-text-tertiary uppercase tracking-wider mb-1.5">Summary</p>
                <p className="text-sm text-text-secondary">{replay.data?.summary ?? 'No summary available.'}</p>
              </div>
              {(replay.data?.prs?.length ?? 0) > 0 && (
                <div>
                  <p className="text-xs font-medium text-text-tertiary uppercase tracking-wider mb-1.5">Pull Requests</p>
                  <div className="flex flex-wrap gap-2">
                    {replay.data?.prs.map((pr) => (
                      <a key={pr.number} href={pr.url} target="_blank" rel="noreferrer"
                        className="text-xs text-accent hover:underline bg-bg-elevated border border-border rounded px-2 py-0.5"
                      >
                        #{pr.number} {pr.title}
                      </a>
                    ))}
                  </div>
                </div>
              )}
              {diff.data && (
                <div>
                  <p className="text-xs font-medium text-text-tertiary uppercase tracking-wider mb-1.5">Diff</p>
                  <p className="text-xs text-text-secondary">
                    {diff.data.files_changed} files &mdash; +{diff.data.lines_added} / -{diff.data.lines_removed}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function Sessions() {
  const { data, isLoading } = useSessions();
  return (
    <div className="p-8 max-w-[1280px]">
      <SectionHeader title="Sessions" sub="Every night the AI ran" />
      <div className="bg-bg-surface border border-border rounded-md overflow-hidden">
        {isLoading
          ? <SkeletonBlock className="h-64 w-full" />
          : [...(data ?? [])].reverse().map((s) => (
            <SessionRow key={s.session} {...s} />
          ))
        }
      </div>
    </div>
  );
}
```

---

### Task 9: Health View

**Files:**
- Create: `dashboard/src/views/Health.tsx`

```tsx
import { useState } from 'react';
import { useHealth } from '../api';
import { GradeChip } from '../components/GradeChip';
import { SectionHeader } from '../components/SectionHeader';
import { SkeletonBlock } from '../components/SkeletonBlock';
import { ErrorMessage } from '../components/ErrorMessage';
import { ChevronUp, ChevronDown } from 'lucide-react';

type SortKey = 'file' | 'score' | 'grade';

export function Health() {
  const { data, isLoading, error, refetch } = useHealth();
  const [sortKey, setSortKey] = useState<SortKey>('score');
  const [sortAsc, setSortAsc] = useState(false);

  const toggle = (k: SortKey) => {
    if (sortKey === k) setSortAsc(!sortAsc);
    else { setSortKey(k); setSortAsc(k === 'file'); }
  };

  const sorted = [...(data?.files ?? [])].sort((a, b) => {
    const av = a[sortKey];
    const bv = b[sortKey];
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return sortAsc ? cmp : -cmp;
  });

  const SortIcon = ({ k }: { k: SortKey }) =>
    sortKey === k ? (
      sortAsc ? <ChevronUp size={12} /> : <ChevronDown size={12} />
    ) : null;

  return (
    <div className="p-8 max-w-[1280px]">
      <SectionHeader
        title="Code Health"
        sub={data ? `Overall: ${data.overall_score}/100 — ${data.files.length} files analyzed` : 'Loading…'}
      />
      {error && <ErrorMessage message={String(error)} onRetry={refetch} />}
      {isLoading ? (
        <SkeletonBlock className="h-64 w-full" />
      ) : (
        <div className="bg-bg-surface border border-border rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr>
                {(['file', 'score', 'grade'] as SortKey[]).map((k) => (
                  <th
                    key={k}
                    onClick={() => toggle(k)}
                    className="cursor-pointer select-none px-4 py-3 text-left text-[11px] font-medium text-text-tertiary uppercase tracking-wider border-b border-border hover:text-text-secondary"
                  >
                    <span className="flex items-center gap-1">{k} <SortIcon k={k} /></span>
                  </th>
                ))}
                <th className="px-4 py-3 text-left text-[11px] font-medium text-text-tertiary uppercase tracking-wider border-b border-border">Issues</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((f) => (
                <tr key={f.file} className="border-b border-border last:border-0 hover:bg-bg-elevated/50">
                  <td className="px-4 py-2.5 font-mono text-xs text-text-secondary">{f.file}</td>
                  <td className="px-4 py-2.5 text-text-primary font-medium">{f.score}</td>
                  <td className="px-4 py-2.5"><GradeChip grade={f.grade} /></td>
                  <td className="px-4 py-2.5 text-xs text-text-tertiary">{f.issues.join(', ') || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
```

---

### Task 10: Coverage View

**Files:**
- Create: `dashboard/src/views/Coverage.tsx`

```tsx
import { useCoverage } from '../api';
import { SectionHeader } from '../components/SectionHeader';
import { SkeletonBlock } from '../components/SkeletonBlock';
import { ErrorMessage } from '../components/ErrorMessage';

export function Coverage() {
  const { data, isLoading, error, refetch } = useCoverage();

  const max = Math.max(...(data?.trend.map((r) => r.coverage_pct) ?? [100]));

  return (
    <div className="p-8 max-w-[1280px]">
      <SectionHeader
        title="Test Coverage"
        sub={data ? `Current: ${data.current_pct}%` : 'Loading…'}
      />
      {error && <ErrorMessage message={String(error)} onRetry={refetch} />}
      {isLoading ? <SkeletonBlock className="h-48 w-full" /> : (
        <div className="bg-bg-surface border border-border rounded-md p-6 space-y-3">
          {(data?.trend ?? []).map((run) => (
            <div key={run.session} className="flex items-center gap-4">
              <span className="w-16 text-right text-xs font-medium text-text-tertiary">S{run.session}</span>
              <div className="flex-1 bg-bg-elevated rounded h-3 overflow-hidden">
                <div
                  className="h-3 bg-success rounded transition-all"
                  style={{ width: `${(run.coverage_pct / max) * 100}%` }}
                />
              </div>
              <span className="w-12 text-right text-xs text-text-secondary font-mono">{run.coverage_pct}%</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

---

### Task 11: Dependencies View

**Files:**
- Create: `dashboard/src/views/Dependencies.tsx`

```tsx
import { useDepGraph } from '../api';
import { SectionHeader } from '../components/SectionHeader';
import { SkeletonBlock } from '../components/SkeletonBlock';
import { AlertTriangle } from 'lucide-react';

export function Dependencies() {
  const { data, isLoading } = useDepGraph();

  const sorted = Object.entries(data?.fan_in ?? {})
    .sort(([, a], [, b]) => b - a)
    .slice(0, 15);

  return (
    <div className="p-8 max-w-[1280px]">
      <SectionHeader title="Module Dependencies" sub="Import relationships between source files" />

      {isLoading ? <SkeletonBlock className="h-64 w-full" /> : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Fan-in ranking */}
          <div className="bg-bg-surface border border-border rounded-md overflow-hidden">
            <div className="px-4 py-3 border-b border-border text-xs font-semibold text-text-tertiary uppercase tracking-wider">Most Imported (Fan-in)</div>
            <div className="p-4 space-y-2.5">
              {sorted.map(([mod, count]) => (
                <div key={mod} className="flex items-center gap-3">
                  <span className="w-40 text-right text-xs font-mono text-text-secondary truncate" title={mod}>{mod}</span>
                  <div className="flex-1 bg-bg-elevated rounded h-2">
                    <div className="bg-accent h-2 rounded" style={{ width: `${(count / sorted[0][1]) * 100}%` }} />
                  </div>
                  <span className="w-6 text-right text-xs text-text-tertiary">{count}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Cycles */}
          <div className="bg-bg-surface border border-border rounded-md overflow-hidden">
            <div className="px-4 py-3 border-b border-border text-xs font-semibold text-text-tertiary uppercase tracking-wider">Circular Dependencies</div>
            <div className="p-4">
              {(data?.cycles.length ?? 0) === 0 ? (
                <p className="text-sm text-success">No cycles detected</p>
              ) : (
                <div className="space-y-2">
                  {data?.cycles.map((cycle, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs text-error">
                      <AlertTriangle size={13} className="mt-0.5 flex-shrink-0" />
                      <span className="font-mono">{cycle.join(' → ')}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

---

### Task 12: Brain View

**Files:**
- Create: `dashboard/src/views/Brain.tsx`

```tsx
import { usePlan, useTriage } from '../api';
import { SectionHeader } from '../components/SectionHeader';
import { SkeletonBlock } from '../components/SkeletonBlock';

const PRIORITY_COLORS = {
  high: 'bg-error/15 text-error',
  medium: 'bg-warning/15 text-warning',
  low: 'bg-bg-elevated text-text-tertiary',
};

export function Brain() {
  const plan = usePlan();
  const triage = useTriage();

  return (
    <div className="p-8 max-w-[1280px]">
      <SectionHeader title="Brain" sub="AI task prioritization and issue triage" />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Task ranking */}
        <div className="bg-bg-surface border border-border rounded-md overflow-hidden">
          <div className="px-4 py-3 border-b border-border text-xs font-semibold text-text-tertiary uppercase tracking-wider">Task Candidates</div>
          {plan.isLoading ? <SkeletonBlock className="h-48 w-full" /> : (
            <div className="divide-y divide-border">
              {(plan.data?.tasks ?? []).map((task) => (
                <div key={task.rank} className="px-4 py-3">
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-xs font-bold text-text-tertiary w-5">#{task.rank}</span>
                    <span className="text-sm text-text-primary">{task.action}</span>
                    <span className="ml-auto text-xs font-mono text-accent">{task.score.toFixed(1)}</span>
                  </div>
                  <div className="flex gap-1.5 ml-7">
                    {(['urgency', 'roadmap', 'health', 'complexity', 'synergy'] as const).map((dim) => (
                      <div key={dim} className="flex-1">
                        <div className="text-[10px] text-text-tertiary mb-0.5">{dim.slice(0, 3)}</div>
                        <div className="bg-bg-elevated rounded-full h-1.5">
                          <div className="bg-accent/60 h-1.5 rounded-full" style={{ width: `${task[dim] * 10}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Issue triage */}
        <div className="bg-bg-surface border border-border rounded-md overflow-hidden">
          <div className="px-4 py-3 border-b border-border text-xs font-semibold text-text-tertiary uppercase tracking-wider">Issue Triage</div>
          {triage.isLoading ? <SkeletonBlock className="h-48 w-full" /> : (
            <div className="divide-y divide-border">
              {(triage.data?.issues ?? []).map((issue) => (
                <div key={issue.number} className="px-4 py-3 flex items-start gap-3">
                  <span className={`inline-block text-[10px] font-bold px-1.5 py-0.5 rounded ${PRIORITY_COLORS[issue.priority]}`}>
                    {issue.priority}
                  </span>
                  <div className="flex-1 min-w-0">
                    <a href={issue.url} target="_blank" rel="noreferrer" className="text-sm text-text-primary hover:text-accent truncate block">
                      #{issue.number} {issue.title}
                    </a>
                    <div className="flex gap-1 mt-1">
                      {issue.labels.map((l) => (
                        <span key={l} className="text-[10px] bg-bg-elevated border border-border rounded px-1.5 py-0.5 text-text-tertiary">{l}</span>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
```

---

### Task 13: Diagnostics View

**Files:**
- Create: `dashboard/src/views/Diagnostics.tsx`

```tsx
import { useDoctor, useTodos, useScores } from '../api';
import { GradeChip } from '../components/GradeChip';
import { SectionHeader } from '../components/SectionHeader';
import { SkeletonBlock } from '../components/SkeletonBlock';
import { CheckCircle2, AlertTriangle, XCircle } from 'lucide-react';

const STATUS_ICON = {
  pass: <CheckCircle2 size={14} className="text-success" />,
  warn: <AlertTriangle size={14} className="text-warning" />,
  fail: <XCircle size={14} className="text-error" />,
};

export function Diagnostics() {
  const doctor = useDoctor();
  const todos = useTodos();
  const scores = useScores();

  return (
    <div className="p-8 max-w-[1280px]">
      <SectionHeader title="Diagnostics" sub="Environment checks, stale TODO items, and PR quality grades" />

      <div className="space-y-6">
        {/* Doctor checks */}
        <div className="bg-bg-surface border border-border rounded-md overflow-hidden">
          <div className="px-4 py-3 border-b border-border text-xs font-semibold text-text-tertiary uppercase tracking-wider">Environment Checks</div>
          {doctor.isLoading ? <SkeletonBlock className="h-32 w-full" /> : (
            <div className="divide-y divide-border">
              {(doctor.data?.checks ?? []).map((check) => (
                <div key={check.name} className="px-4 py-3 flex items-start gap-3">
                  {STATUS_ICON[check.status]}
                  <div>
                    <p className="text-sm font-medium text-text-primary">{check.name}</p>
                    <p className="text-xs text-text-tertiary mt-0.5">{check.detail}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Stale TODOs */}
        <div className="bg-bg-surface border border-border rounded-md overflow-hidden">
          <div className="px-4 py-3 border-b border-border text-xs font-semibold text-text-tertiary uppercase tracking-wider">Stale TODO Items</div>
          {todos.isLoading ? <SkeletonBlock className="h-32 w-full" /> : (
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <th className="px-4 py-2.5 text-left text-[11px] font-medium text-text-tertiary uppercase tracking-wider border-b border-border">File:Line</th>
                  <th className="px-4 py-2.5 text-left text-[11px] font-medium text-text-tertiary uppercase tracking-wider border-b border-border">Text</th>
                  <th className="px-4 py-2.5 text-left text-[11px] font-medium text-text-tertiary uppercase tracking-wider border-b border-border">Age</th>
                </tr>
              </thead>
              <tbody>
                {(todos.data?.todos ?? []).map((t, i) => (
                  <tr key={i} className="border-b border-border last:border-0">
                    <td className="px-4 py-2.5 font-mono text-xs text-text-secondary">{t.file}:{t.line}</td>
                    <td className="px-4 py-2.5 text-xs text-text-tertiary max-w-[400px] truncate">{t.text}</td>
                    <td className="px-4 py-2.5 text-xs text-text-tertiary">{t.age_days}d</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* PR scores */}
        <div className="bg-bg-surface border border-border rounded-md overflow-hidden">
          <div className="px-4 py-3 border-b border-border text-xs font-semibold text-text-tertiary uppercase tracking-wider">PR Quality Grades</div>
          {scores.isLoading ? <SkeletonBlock className="h-32 w-full" /> : (
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <th className="px-4 py-2.5 text-left text-[11px] font-medium text-text-tertiary uppercase tracking-wider border-b border-border">PR</th>
                  <th className="px-4 py-2.5 text-left text-[11px] font-medium text-text-tertiary uppercase tracking-wider border-b border-border">Score</th>
                  <th className="px-4 py-2.5 text-left text-[11px] font-medium text-text-tertiary uppercase tracking-wider border-b border-border">Grade</th>
                </tr>
              </thead>
              <tbody>
                {(scores.data?.prs ?? []).map((pr) => (
                  <tr key={pr.pr} className="border-b border-border last:border-0">
                    <td className="px-4 py-2.5 text-text-secondary">#{pr.pr} {pr.title}</td>
                    <td className="px-4 py-2.5 font-mono text-text-primary">{pr.score}</td>
                    <td className="px-4 py-2.5"><GradeChip grade={pr.grade} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
```

---

### Task 14: Final App.tsx Wiring + Build Verification

**Files:**
- Update: `dashboard/src/App.tsx`

**Step 1: Replace placeholder App.tsx with wired version**

```tsx
import { Routes, Route } from 'react-router-dom';
import { Sidebar } from './components/Sidebar';
import { Overview } from './views/Overview';
import { Sessions } from './views/Sessions';
import { Health } from './views/Health';
import { Coverage } from './views/Coverage';
import { Dependencies } from './views/Dependencies';
import { Brain } from './views/Brain';
import { Diagnostics } from './views/Diagnostics';

export default function App() {
  return (
    <div className="flex min-h-screen bg-bg-primary">
      <Sidebar />
      <main className="ml-[200px] flex-1">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/sessions" element={<Sessions />} />
          <Route path="/health" element={<Health />} />
          <Route path="/coverage" element={<Coverage />} />
          <Route path="/deps" element={<Dependencies />} />
          <Route path="/brain" element={<Brain />} />
          <Route path="/diagnostics" element={<Diagnostics />} />
        </Routes>
      </main>
    </div>
  );
}
```

**Step 2: TypeScript check**

Run: `cd /Users/gunnar/Documents/Dev/awake/dashboard && npx tsc --noEmit`
Expected: No TypeScript errors

**Step 3: Build**

Run: `cd /Users/gunnar/Documents/Dev/awake/dashboard && npm run build`
Expected: `docs/dashboard/` created with `index.html` and assets

---

### Task 15: Integration Test — End to End

**Step 1: Start API server in background**

```bash
cd /Users/gunnar/Documents/Dev/awake
python -m src.cli dashboard --no-browser &
```

**Step 2: Wait 2 seconds, then hit each endpoint**

```bash
sleep 2
curl -s http://localhost:8710/api/health | python -m json.tool | head -20
curl -s http://localhost:8710/api/stats | python -m json.tool | head -10
curl -s http://localhost:8710/api/unknown
```

Expected:
- `/api/health` → JSON with `score` key
- `/api/stats` → JSON with `nights_run` key
- `/api/unknown` → `{"error": "Unknown route: /api/unknown"}` with 404

**Step 3: Start Vite dev server**

```bash
cd /Users/gunnar/Documents/Dev/awake/dashboard && npm run dev -- --port 5173
```

Expected: Vite starts, opens browser (or navigate to http://localhost:5173)
Verify: All 7 nav items load without console errors

**Step 4: Kill background server, commit any fixes**

```bash
kill %1
```

**Step 5: Final commit**

```bash
cd /Users/gunnar/Documents/Dev/awake
git add -A
git commit -m "chore: integration verification complete"
```
