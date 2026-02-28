# Live Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a real-time dashboard for nightshift with a Python API server and React + Vite frontend styled like Linear.

**Architecture:** Two-process model — `src/server.py` wraps all CLI `--json` outputs as HTTP endpoints; `dashboard/` is a React SPA that fetches from those endpoints. The `nightshift dashboard` CLI command launches both.

**Tech Stack:** Python stdlib `http.server` (backend), React 18 + TypeScript + Vite + Tailwind CSS + TanStack Query + React Router + Lucide React (frontend).

---

### Task 1: API Server — Core HTTP Handler

**Files:**
- Create: `src/server.py`
- Create: `tests/test_server.py`

**Step 1: Write failing test for server request handler**

```python
"""Tests for src/server.py — the Nightshift dashboard API server."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from http.server import HTTPServer
from io import BytesIO

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.server import NightshiftHandler


class MockRequest:
    """Minimal mock for an HTTP request."""

    def __init__(self, path: str):
        self.path = path

    def makefile(self, *args, **kwargs):
        return BytesIO()


def make_handler(path: str) -> NightshiftHandler:
    """Create a handler with a mocked request for the given path."""
    handler = NightshiftHandler.__new__(NightshiftHandler)
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

Run: `cd /Users/gunnar/Documents/Dev/nightshift && python -m pytest tests/test_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.server'`

**Step 3: Write the server implementation**

```python
"""HTTP API server for the Nightshift dashboard.

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


class NightshiftHandler(BaseHTTPRequestHandler):
    """HTTP request handler that dispatches to nightshift CLI commands."""

    def _run_command(self, cli_args: list[str]) -> str:
        """Run a nightshift CLI command and return stdout."""
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
        self._send_json(204, "")

    def do_GET(self) -> None:
        """Route GET requests to CLI commands."""
        # Static routes
        if self.path in ROUTE_MAP:
            try:
                output = self._run_command(ROUTE_MAP[self.path])
                self._send_json(200, output)
            except Exception as exc:
                self._send_json(500, json.dumps({"error": str(exc)}))
            return

        # Parameterized routes
        for pattern, (cmd, base_args) in PARAMETERIZED_ROUTES.items():
            match = re.match(pattern, self.path)
            if match:
                session_num = match.group(1)
                try:
                    output = self._run_command([cmd] + base_args + [session_num])
                    self._send_json(200, output)
                except Exception as exc:
                    self._send_json(500, json.dumps({"error": str(exc)}))
                return

        # Sessions list (derived from replay)
        if self.path == "/api/sessions":
            try:
                from src.stats import compute_stats
                repo = getattr(self.server, "repo_path", Path("."))
                stats = compute_stats(
                    repo_path=repo, log_path=repo / "NIGHTSHIFT_LOG.md"
                )
                self._send_json(200, json.dumps({
                    "sessions": stats.to_dict().get("sessions", []),
                    "total": len(stats.sessions),
                }))
            except Exception as exc:
                self._send_json(500, json.dumps({"error": str(exc)}))
            return

        # 404
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"error": "Not found"}).encode("utf-8"))

    def log_message(self, format: str, *args) -> None:
        """Suppress default logging to stderr."""
        pass


def start_server(
    port: int = 8710,
    repo_path: Optional[Path] = None,
    open_browser: bool = True,
) -> None:
    """Start the dashboard API server."""
    server = HTTPServer(("127.0.0.1", port), NightshiftHandler)
    server.repo_path = repo_path or Path(__file__).resolve().parent.parent  # type: ignore[attr-defined]
    print(f"Nightshift API server running on http://127.0.0.1:{port}")
    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/gunnar/Documents/Dev/nightshift && python -m pytest tests/test_server.py -v`
Expected: PASS (all 4 tests)

**Step 5: Commit**

```bash
cd /Users/gunnar/Documents/Dev/nightshift
git add src/server.py tests/test_server.py
git commit -m "feat: add API server wrapping CLI commands as JSON endpoints"
```

---

### Task 2: Register `dashboard` CLI Subcommand

**Files:**
- Modify: `src/cli.py`
- Modify: `tests/test_cli.py`

**Step 1: Write failing test for dashboard subcommand parsing**

Add to `tests/test_cli.py`:

```python
def test_dashboard_subcommand_parses(self):
    parser = build_parser()
    args = parser.parse_args(["dashboard"])
    assert args.command == "dashboard"

def test_dashboard_custom_port(self):
    parser = build_parser()
    args = parser.parse_args(["dashboard", "--port", "9000"])
    assert args.port == 9000

def test_dashboard_default_port(self):
    parser = build_parser()
    args = parser.parse_args(["dashboard"])
    assert args.port == 8710
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/gunnar/Documents/Dev/nightshift && python -m pytest tests/test_cli.py::TestBuildParser::test_dashboard_subcommand_parses -v`
Expected: FAIL — SystemExit (unrecognized command)

**Step 3: Add dashboard subcommand to cli.py**

Add the `cmd_dashboard` function before `build_parser` in `src/cli.py`:

```python
def cmd_dashboard(args: argparse.Namespace) -> int:
    """Launch the dashboard API server."""
    from src.server import start_server

    repo = _repo(getattr(args, "repo", None))
    _print_header("Dashboard")
    _print_info(f"Starting API server on port {args.port}...")
    start_server(port=args.port, repo_path=repo)
    return 0
```

Add to `build_parser()` before the `run` subparser:

```python
# dashboard
p_dash = sub.add_parser("dashboard", help="Launch live dashboard")
p_dash.add_argument("--port", type=int, default=8710, help="API server port (default: 8710)")
p_dash.set_defaults(func=cmd_dashboard)
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/gunnar/Documents/Dev/nightshift && python -m pytest tests/test_cli.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /Users/gunnar/Documents/Dev/nightshift
git add src/cli.py tests/test_cli.py
git commit -m "feat: add 'nightshift dashboard' CLI subcommand"
```

---

### Task 3: Scaffold React + Vite Frontend

**Files:**
- Create: `dashboard/` directory (via `npm create vite`)
- Modify: `dashboard/package.json` (add deps)
- Modify: `dashboard/vite.config.ts` (proxy)
- Modify: `dashboard/tailwind.config.js` (theme)

**Step 1: Create Vite project**

```bash
cd /Users/gunnar/Documents/Dev/nightshift
npm create vite@latest dashboard -- --template react-ts
```

**Step 2: Install dependencies**

```bash
cd /Users/gunnar/Documents/Dev/nightshift/dashboard
npm install
npm install -D tailwindcss @tailwindcss/vite
npm install @tanstack/react-query react-router-dom lucide-react
```

**Step 3: Configure Tailwind**

Replace `dashboard/src/index.css` with:

```css
@import "tailwindcss";

@theme {
  --color-bg-primary: #0a0a0b;
  --color-bg-surface: #141415;
  --color-bg-elevated: #1c1c1e;
  --color-border: #2a2a2d;
  --color-text-primary: #ededef;
  --color-text-secondary: #8a8a8e;
  --color-text-tertiary: #5c5c60;
  --color-accent: #6e6afa;
  --color-success: #45d483;
  --color-warning: #f0b232;
  --color-error: #ef5f5f;

  --font-sans: "Inter", ui-sans-serif, system-ui, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, monospace;
}

body {
  background-color: var(--color-bg-primary);
  color: var(--color-text-primary);
  font-family: var(--font-sans);
  -webkit-font-smoothing: antialiased;
}
```

**Step 4: Configure Vite proxy**

Replace `dashboard/vite.config.ts`:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8710",
        changeOrigin: true,
      },
    },
  },
});
```

**Step 5: Clean up Vite defaults**

Delete: `dashboard/src/App.css`, `dashboard/public/vite.svg`, `dashboard/src/assets/react.svg`

Replace `dashboard/src/App.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { Overview } from "./views/Overview";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchInterval: 30_000,
      staleTime: 10_000,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="flex h-screen">
          <Sidebar />
          <main className="flex-1 overflow-y-auto p-8">
            <Routes>
              <Route path="/" element={<Navigate to="/overview" replace />} />
              <Route path="/overview" element={<Overview />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
```

**Step 6: Verify it builds**

Run: `cd /Users/gunnar/Documents/Dev/nightshift/dashboard && npm run build`
Expected: Build succeeds (may have TS errors for missing components — that's fine, we'll create them next)

**Step 7: Commit**

```bash
cd /Users/gunnar/Documents/Dev/nightshift
git add dashboard/
git commit -m "feat: scaffold React + Vite dashboard with Tailwind theme"
```

---

### Task 4: Sidebar Component + Layout Shell

**Files:**
- Create: `dashboard/src/components/Sidebar.tsx`

**Step 1: Create sidebar component**

```tsx
import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Clock,
  HeartPulse,
  TestTubeDiagonal,
  GitFork,
  Brain,
  Stethoscope,
} from "lucide-react";

const NAV_ITEMS = [
  { to: "/overview", label: "Overview", icon: LayoutDashboard },
  { to: "/sessions", label: "Sessions", icon: Clock },
  { to: "/health", label: "Health", icon: HeartPulse },
  { to: "/coverage", label: "Coverage", icon: TestTubeDiagonal },
  { to: "/dependencies", label: "Dependencies", icon: GitFork },
  { to: "/brain", label: "Brain", icon: Brain },
  { to: "/diagnostics", label: "Diagnostics", icon: Stethoscope },
];

export function Sidebar() {
  return (
    <aside className="w-52 shrink-0 border-r border-border bg-bg-surface flex flex-col">
      <div className="px-4 py-5">
        <span className="text-sm font-semibold tracking-tight text-text-primary">
          nightshift
        </span>
      </div>
      <nav className="flex-1 px-2 space-y-0.5">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] font-medium transition-colors ${
                isActive
                  ? "bg-accent/10 text-accent"
                  : "text-text-secondary hover:text-text-primary hover:bg-bg-elevated"
              }`
            }
          >
            <Icon size={16} strokeWidth={1.75} />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
```

**Step 2: Verify it compiles**

Run: `cd /Users/gunnar/Documents/Dev/nightshift/dashboard && npx tsc --noEmit`
Expected: PASS (no type errors)

**Step 3: Commit**

```bash
cd /Users/gunnar/Documents/Dev/nightshift
git add dashboard/src/components/Sidebar.tsx
git commit -m "feat: add sidebar navigation component"
```

---

### Task 5: API Fetch Hooks

**Files:**
- Create: `dashboard/src/api/hooks.ts`

**Step 1: Create all API hooks**

```ts
import { useQuery } from "@tanstack/react-query";

async function fetchApi<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: () => fetchApi("/api/health") });
}

export function useStats() {
  return useQuery({ queryKey: ["stats"], queryFn: () => fetchApi("/api/stats") });
}

export function useCoverage() {
  return useQuery({ queryKey: ["coverage"], queryFn: () => fetchApi("/api/coverage") });
}

export function useChangelog() {
  return useQuery({ queryKey: ["changelog"], queryFn: () => fetchApi("/api/changelog") });
}

export function useScores() {
  return useQuery({ queryKey: ["scores"], queryFn: () => fetchApi("/api/scores") });
}

export function useDepGraph() {
  return useQuery({ queryKey: ["depgraph"], queryFn: () => fetchApi("/api/depgraph") });
}

export function useDoctor() {
  return useQuery({ queryKey: ["doctor"], queryFn: () => fetchApi("/api/doctor") });
}

export function useTodos() {
  return useQuery({ queryKey: ["todos"], queryFn: () => fetchApi("/api/todos") });
}

export function useTriage() {
  return useQuery({ queryKey: ["triage"], queryFn: () => fetchApi("/api/triage") });
}

export function usePlan() {
  return useQuery({ queryKey: ["plan"], queryFn: () => fetchApi("/api/plan") });
}

export function useSessions() {
  return useQuery({ queryKey: ["sessions"], queryFn: () => fetchApi("/api/sessions") });
}

export function useReplay(session: number) {
  return useQuery({
    queryKey: ["replay", session],
    queryFn: () => fetchApi(`/api/replay/${session}`),
    enabled: session > 0,
  });
}

export function useDiff(session: number) {
  return useQuery({
    queryKey: ["diff", session],
    queryFn: () => fetchApi(`/api/diff/${session}`),
    enabled: session > 0,
  });
}
```

**Step 2: Commit**

```bash
cd /Users/gunnar/Documents/Dev/nightshift
git add dashboard/src/api/hooks.ts
git commit -m "feat: add TanStack Query hooks for all API endpoints"
```

---

### Task 6: Shared UI Primitives

**Files:**
- Create: `dashboard/src/components/StatCard.tsx`
- Create: `dashboard/src/components/DataTable.tsx`
- Create: `dashboard/src/components/Badge.tsx`
- Create: `dashboard/src/components/PageHeader.tsx`
- Create: `dashboard/src/components/Skeleton.tsx`

**Step 1: Create StatCard**

```tsx
import type { ReactNode } from "react";

interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  icon?: ReactNode;
}

export function StatCard({ label, value, sub, icon }: StatCardProps) {
  return (
    <div className="rounded-md border border-border bg-bg-surface p-5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-text-tertiary">
          {label}
        </span>
        {icon && <span className="text-text-tertiary">{icon}</span>}
      </div>
      <div className="mt-2 text-2xl font-semibold tabular-nums text-text-primary">
        {value}
      </div>
      {sub && <div className="mt-0.5 text-xs text-text-tertiary">{sub}</div>}
    </div>
  );
}
```

**Step 2: Create DataTable**

```tsx
interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => React.ReactNode;
  align?: "left" | "right";
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyFn: (row: T) => string;
}

export function DataTable<T>({ columns, data, keyFn }: DataTableProps<T>) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="border-b border-border">
            {columns.map((col) => (
              <th
                key={col.key}
                className={`px-3 py-2 font-medium text-xs uppercase tracking-wider text-text-tertiary ${
                  col.align === "right" ? "text-right" : "text-left"
                }`}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr key={keyFn(row)} className="border-b border-border last:border-0">
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={`px-3 py-2.5 ${
                    col.align === "right" ? "text-right" : "text-left"
                  }`}
                >
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

**Step 3: Create Badge**

```tsx
const VARIANTS = {
  success: "bg-success/15 text-success",
  warning: "bg-warning/15 text-warning",
  error: "bg-error/15 text-error",
  neutral: "bg-bg-elevated text-text-secondary",
  accent: "bg-accent/15 text-accent",
} as const;

interface BadgeProps {
  variant: keyof typeof VARIANTS;
  children: React.ReactNode;
}

export function Badge({ variant, children }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-semibold ${VARIANTS[variant]}`}
    >
      {children}
    </span>
  );
}
```

**Step 4: Create PageHeader**

```tsx
interface PageHeaderProps {
  title: string;
  description?: string;
}

export function PageHeader({ title, description }: PageHeaderProps) {
  return (
    <div className="mb-6">
      <h1 className="text-lg font-semibold text-text-primary">{title}</h1>
      {description && (
        <p className="mt-1 text-sm text-text-secondary">{description}</p>
      )}
    </div>
  );
}
```

**Step 5: Create Skeleton**

```tsx
export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded bg-bg-elevated ${className}`}
    />
  );
}

export function StatCardSkeleton() {
  return (
    <div className="rounded-md border border-border bg-bg-surface p-5">
      <Skeleton className="h-3 w-16 mb-3" />
      <Skeleton className="h-7 w-20 mb-1" />
      <Skeleton className="h-3 w-24" />
    </div>
  );
}

export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-8 w-full" />
      ))}
    </div>
  );
}
```

**Step 6: Commit**

```bash
cd /Users/gunnar/Documents/Dev/nightshift
git add dashboard/src/components/
git commit -m "feat: add shared UI primitives — StatCard, DataTable, Badge, PageHeader, Skeleton"
```

---

### Task 7: Overview View

**Files:**
- Create: `dashboard/src/views/Overview.tsx`

**Step 1: Implement Overview page**

```tsx
import {
  Clock,
  GitPullRequest,
  Blocks,
  TestTubeDiagonal,
  TrendingUp,
} from "lucide-react";
import { useStats, useHealth, useCoverage } from "../api/hooks";
import { StatCard } from "../components/StatCard";
import { PageHeader } from "../components/PageHeader";
import { Badge } from "../components/Badge";
import { StatCardSkeleton } from "../components/Skeleton";

function healthBadge(score: number) {
  if (score >= 85) return <Badge variant="success">Excellent</Badge>;
  if (score >= 70) return <Badge variant="warning">Good</Badge>;
  return <Badge variant="error">Needs work</Badge>;
}

export function Overview() {
  const stats = useStats();
  const health = useHealth();
  const coverage = useCoverage();

  const s = stats.data as any;
  const h = health.data as any;

  return (
    <div className="max-w-5xl">
      <PageHeader
        title="Overview"
        description="Real-time snapshot of the nightshift autonomous development system."
      />

      <div className="grid grid-cols-5 gap-4 mb-8">
        {stats.isLoading ? (
          Array.from({ length: 5 }).map((_, i) => <StatCardSkeleton key={i} />)
        ) : (
          <>
            <StatCard
              label="Sessions"
              value={s?.nights_active ?? "—"}
              sub="Nights active"
              icon={<Clock size={15} />}
            />
            <StatCard
              label="PRs"
              value={s?.total_prs ?? "—"}
              sub="Merged"
              icon={<GitPullRequest size={15} />}
            />
            <StatCard
              label="Modules"
              value={h?.files ? Object.keys(h.files).length : "—"}
              sub="in src/"
              icon={<Blocks size={15} />}
            />
            <StatCard
              label="Tests"
              value={s?.total_commits ?? "—"}
              sub="Total commits"
              icon={<TestTubeDiagonal size={15} />}
            />
            <StatCard
              label="Health"
              value={h?.overall_health_score != null ? `${Math.round(h.overall_health_score)}` : "—"}
              sub={h?.overall_health_score != null ? undefined : "Loading..."}
              icon={<TrendingUp size={15} />}
            />
          </>
        )}
      </div>

      {h?.overall_health_score != null && (
        <div className="rounded-md border border-border bg-bg-surface p-5 mb-6">
          <div className="flex items-center justify-between mb-4">
            <span className="text-sm font-medium text-text-primary">Overall Health</span>
            {healthBadge(h.overall_health_score)}
          </div>
          <div className="h-2 rounded-full bg-bg-elevated overflow-hidden">
            <div
              className="h-full rounded-full bg-accent transition-all duration-500"
              style={{ width: `${h.overall_health_score}%` }}
            />
          </div>
          <div className="mt-2 text-xs text-text-tertiary tabular-nums">
            {Math.round(h.overall_health_score)} / 100
          </div>
        </div>
      )}

      {s?.sessions && s.sessions.length > 0 && (
        <div className="rounded-md border border-border bg-bg-surface">
          <div className="px-4 py-3 border-b border-border">
            <span className="text-xs font-medium uppercase tracking-wider text-text-tertiary">
              Recent Sessions
            </span>
          </div>
          <div className="divide-y divide-border">
            {[...s.sessions].reverse().slice(0, 5).map((session: any, i: number) => (
              <div key={i} className="flex items-center gap-3 px-4 py-3">
                <span className="shrink-0 rounded bg-bg-elevated px-2 py-0.5 text-[11px] font-semibold text-accent tabular-nums">
                  S{session.session ?? i}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] text-text-primary truncate">
                    {session.title ?? `Session ${session.session ?? i}`}
                  </div>
                  <div className="text-xs text-text-tertiary">
                    {session.date ?? "—"} — {session.prs ?? 0} PRs
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

**Step 2: Verify it compiles**

Run: `cd /Users/gunnar/Documents/Dev/nightshift/dashboard && npx tsc --noEmit`
Expected: PASS

**Step 3: Commit**

```bash
cd /Users/gunnar/Documents/Dev/nightshift
git add dashboard/src/views/Overview.tsx
git commit -m "feat: add Overview view with stat cards, health gauge, session list"
```

---

### Task 8: Sessions View

**Files:**
- Create: `dashboard/src/views/Sessions.tsx`
- Modify: `dashboard/src/App.tsx` (add route)

**Step 1: Implement Sessions page**

```tsx
import { useState } from "react";
import { ChevronRight, GitPullRequest, CheckCircle2 } from "lucide-react";
import { useSessions, useReplay } from "../api/hooks";
import { PageHeader } from "../components/PageHeader";
import { Badge } from "../components/Badge";
import { TableSkeleton } from "../components/Skeleton";

function SessionDetail({ session }: { session: number }) {
  const { data, isLoading } = useReplay(session);
  const d = data as any;

  if (isLoading) return <TableSkeleton rows={3} />;
  if (!d) return <div className="text-sm text-text-tertiary">No data</div>;

  return (
    <div className="space-y-4 py-3">
      {d.narrative && (
        <p className="text-[13px] text-text-secondary leading-relaxed">{d.narrative}</p>
      )}

      {d.tasks?.length > 0 && (
        <div>
          <div className="text-xs font-medium uppercase tracking-wider text-text-tertiary mb-2">
            Tasks
          </div>
          <div className="space-y-1.5">
            {d.tasks.map((t: any, i: number) => (
              <div key={i} className="flex items-center gap-2 text-[13px]">
                <CheckCircle2 size={14} className="text-success shrink-0" />
                <span className="text-text-primary">{t.name ?? t}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {d.prs?.length > 0 && (
        <div>
          <div className="text-xs font-medium uppercase tracking-wider text-text-tertiary mb-2">
            Pull Requests
          </div>
          <div className="space-y-1.5">
            {d.prs.map((pr: any, i: number) => (
              <div key={i} className="flex items-center gap-2 text-[13px]">
                <GitPullRequest size={14} className="text-accent shrink-0" />
                <span className="text-text-primary">{pr.title ?? `PR #${pr.number}`}</span>
                {pr.number && (
                  <span className="text-text-tertiary">#{pr.number}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {d.stats_snapshot && (
        <div className="flex gap-4 text-xs text-text-tertiary">
          {d.stats_snapshot.lines_changed != null && (
            <span>{d.stats_snapshot.lines_changed} lines changed</span>
          )}
          {d.stats_snapshot.total_commits != null && (
            <span>{d.stats_snapshot.total_commits} commits</span>
          )}
        </div>
      )}
    </div>
  );
}

export function Sessions() {
  const { data, isLoading } = useSessions();
  const [expanded, setExpanded] = useState<number | null>(null);
  const sessions = (data as any)?.sessions ?? [];

  return (
    <div className="max-w-3xl">
      <PageHeader
        title="Sessions"
        description="Timeline of autonomous development sessions."
      />

      {isLoading ? (
        <TableSkeleton rows={6} />
      ) : (
        <div className="rounded-md border border-border bg-bg-surface divide-y divide-border">
          {[...sessions].reverse().map((s: any, i: number) => {
            const num = s.session ?? sessions.length - i;
            const isOpen = expanded === num;
            return (
              <div key={num}>
                <button
                  onClick={() => setExpanded(isOpen ? null : num)}
                  className="flex items-center gap-3 w-full px-4 py-3 text-left hover:bg-bg-elevated transition-colors"
                >
                  <ChevronRight
                    size={14}
                    className={`text-text-tertiary transition-transform ${isOpen ? "rotate-90" : ""}`}
                  />
                  <span className="shrink-0 rounded bg-bg-elevated px-2 py-0.5 text-[11px] font-semibold text-accent tabular-nums">
                    S{num}
                  </span>
                  <div className="flex-1 min-w-0">
                    <span className="text-[13px] font-medium text-text-primary">
                      {s.title ?? `Session ${num}`}
                    </span>
                  </div>
                  <span className="text-xs text-text-tertiary shrink-0">
                    {s.date ?? "—"}
                  </span>
                  {s.prs != null && (
                    <Badge variant="neutral">{s.prs} PRs</Badge>
                  )}
                </button>
                {isOpen && (
                  <div className="px-4 pb-4 pl-12 border-t border-border">
                    <SessionDetail session={num} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
```

**Step 2: Add route to App.tsx**

Add import: `import { Sessions } from "./views/Sessions";`
Add route: `<Route path="/sessions" element={<Sessions />} />`

**Step 3: Commit**

```bash
cd /Users/gunnar/Documents/Dev/nightshift
git add dashboard/src/views/Sessions.tsx dashboard/src/App.tsx
git commit -m "feat: add Sessions view with expandable timeline"
```

---

### Task 9: Health View

**Files:**
- Create: `dashboard/src/views/Health.tsx`
- Modify: `dashboard/src/App.tsx` (add route)

**Step 1: Implement Health page**

```tsx
import { useHealth } from "../api/hooks";
import { PageHeader } from "../components/PageHeader";
import { DataTable } from "../components/DataTable";
import { Badge } from "../components/Badge";
import { TableSkeleton } from "../components/Skeleton";

function scoreBadge(score: number) {
  if (score >= 90) return <Badge variant="success">Excellent</Badge>;
  if (score >= 80) return <Badge variant="success">Good</Badge>;
  if (score >= 70) return <Badge variant="warning">Fair</Badge>;
  return <Badge variant="error">Needs work</Badge>;
}

export function Health() {
  const { data, isLoading } = useHealth();
  const h = data as any;

  const files = h?.files
    ? Object.entries(h.files).map(([path, metrics]: [string, any]) => ({
        path,
        ...metrics,
      }))
    : [];

  const sorted = [...files].sort(
    (a: any, b: any) => (b.health_score ?? 0) - (a.health_score ?? 0)
  );

  const columns = [
    {
      key: "path",
      header: "Module",
      render: (row: any) => (
        <span className="font-mono text-xs text-text-primary">{row.path}</span>
      ),
    },
    {
      key: "score",
      header: "Score",
      align: "right" as const,
      render: (row: any) => (
        <span className="font-mono text-xs tabular-nums">
          {row.health_score != null ? Math.round(row.health_score) : "—"}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (row: any) =>
        row.health_score != null ? scoreBadge(row.health_score) : null,
    },
    {
      key: "functions",
      header: "Functions",
      align: "right" as const,
      render: (row: any) => (
        <span className="text-xs text-text-secondary tabular-nums">
          {row.function_count ?? "—"}
        </span>
      ),
    },
    {
      key: "lines",
      header: "Lines",
      align: "right" as const,
      render: (row: any) => (
        <span className="text-xs text-text-secondary tabular-nums">
          {row.total_lines ?? "—"}
        </span>
      ),
    },
    {
      key: "docstrings",
      header: "Docstring %",
      align: "right" as const,
      render: (row: any) => (
        <span className="text-xs text-text-secondary tabular-nums">
          {row.docstring_coverage != null
            ? `${Math.round(row.docstring_coverage * 100)}%`
            : "—"}
        </span>
      ),
    },
  ];

  return (
    <div className="max-w-5xl">
      <PageHeader
        title="Health"
        description="Per-module code quality scores from static analysis."
      />

      {h?.overall_health_score != null && (
        <div className="flex items-center gap-3 mb-6">
          <span className="text-sm text-text-secondary">Overall:</span>
          <span className="text-lg font-semibold tabular-nums">
            {Math.round(h.overall_health_score)}
          </span>
          <span className="text-sm text-text-tertiary">/ 100</span>
          {scoreBadge(h.overall_health_score)}
        </div>
      )}

      <div className="rounded-md border border-border bg-bg-surface">
        {isLoading ? (
          <div className="p-4">
            <TableSkeleton rows={8} />
          </div>
        ) : (
          <DataTable columns={columns} data={sorted} keyFn={(r: any) => r.path} />
        )}
      </div>
    </div>
  );
}
```

**Step 2: Add route, commit**

```bash
cd /Users/gunnar/Documents/Dev/nightshift
git add dashboard/src/views/Health.tsx dashboard/src/App.tsx
git commit -m "feat: add Health view with sortable module scores table"
```

---

### Task 10: Coverage View

**Files:**
- Create: `dashboard/src/views/Coverage.tsx`
- Modify: `dashboard/src/App.tsx` (add route)

**Step 1: Implement Coverage page**

```tsx
import { useCoverage } from "../api/hooks";
import { PageHeader } from "../components/PageHeader";
import { DataTable } from "../components/DataTable";
import { Badge } from "../components/Badge";
import { TableSkeleton } from "../components/Skeleton";

export function Coverage() {
  const { data, isLoading } = useCoverage();
  const d = data as any;

  const snapshots = d?.snapshots ?? [];
  const latest = snapshots.length > 0 ? snapshots[snapshots.length - 1] : null;

  const columns = [
    {
      key: "session",
      header: "Session",
      render: (row: any) => (
        <span className="font-mono text-xs text-accent tabular-nums">
          S{row.session ?? "—"}
        </span>
      ),
    },
    {
      key: "coverage",
      header: "Coverage",
      align: "right" as const,
      render: (row: any) => (
        <span className="font-mono text-xs tabular-nums">
          {row.total_coverage != null ? `${row.total_coverage.toFixed(1)}%` : "—"}
        </span>
      ),
    },
    {
      key: "lines",
      header: "Covered / Total",
      align: "right" as const,
      render: (row: any) => (
        <span className="text-xs text-text-secondary tabular-nums">
          {row.lines_covered ?? "—"} / {row.lines_total ?? "—"}
        </span>
      ),
    },
  ];

  return (
    <div className="max-w-4xl">
      <PageHeader
        title="Coverage"
        description="Test coverage trends across sessions."
      />

      {latest && (
        <div className="flex items-center gap-4 mb-6">
          <div className="text-2xl font-semibold tabular-nums">
            {latest.total_coverage?.toFixed(1)}%
          </div>
          <Badge variant={latest.total_coverage >= 80 ? "success" : "warning"}>
            Latest
          </Badge>
        </div>
      )}

      {/* Trend bars */}
      {snapshots.length > 0 && (
        <div className="rounded-md border border-border bg-bg-surface p-5 mb-6">
          <div className="text-xs font-medium uppercase tracking-wider text-text-tertiary mb-4">
            Coverage Trend
          </div>
          <div className="flex items-end gap-1.5 h-24">
            {snapshots.map((snap: any, i: number) => {
              const pct = snap.total_coverage ?? 0;
              return (
                <div
                  key={i}
                  className="flex-1 rounded-t bg-accent/60 hover:bg-accent transition-colors"
                  style={{ height: `${pct}%` }}
                  title={`S${snap.session ?? i}: ${pct.toFixed(1)}%`}
                />
              );
            })}
          </div>
        </div>
      )}

      <div className="rounded-md border border-border bg-bg-surface">
        {isLoading ? (
          <div className="p-4"><TableSkeleton rows={5} /></div>
        ) : (
          <DataTable
            columns={columns}
            data={[...snapshots].reverse()}
            keyFn={(r: any) => `s${r.session ?? Math.random()}`}
          />
        )}
      </div>
    </div>
  );
}
```

**Step 2: Add route, commit**

```bash
cd /Users/gunnar/Documents/Dev/nightshift
git add dashboard/src/views/Coverage.tsx dashboard/src/App.tsx
git commit -m "feat: add Coverage view with trend bars and history table"
```

---

### Task 11: Dependencies View

**Files:**
- Create: `dashboard/src/views/Dependencies.tsx`
- Modify: `dashboard/src/App.tsx` (add route)

**Step 1: Implement Dependencies page**

```tsx
import { useDepGraph } from "../api/hooks";
import { PageHeader } from "../components/PageHeader";
import { DataTable } from "../components/DataTable";
import { Badge } from "../components/Badge";
import { TableSkeleton } from "../components/Skeleton";

export function Dependencies() {
  const { data, isLoading } = useDepGraph();
  const d = data as any;

  const modules = d?.modules ?? [];
  const fanIn = d?.fan_in ?? {};
  const cycles = d?.cycles ?? [];

  const enriched = modules.map((m: any) => ({
    ...m,
    fan_in: fanIn[m.name] ?? 0,
    fan_out: m.imports?.length ?? m.fan_out ?? 0,
  }));

  const sorted = [...enriched].sort((a: any, b: any) => b.fan_in - a.fan_in);

  const columns = [
    {
      key: "name",
      header: "Module",
      render: (row: any) => (
        <span className="font-mono text-xs text-text-primary">{row.name}</span>
      ),
    },
    {
      key: "fan_in",
      header: "Fan-in",
      align: "right" as const,
      render: (row: any) => (
        <span className="font-mono text-xs tabular-nums text-accent">
          {row.fan_in}
        </span>
      ),
    },
    {
      key: "fan_out",
      header: "Fan-out",
      align: "right" as const,
      render: (row: any) => (
        <span className="font-mono text-xs tabular-nums">{row.fan_out}</span>
      ),
    },
    {
      key: "lines",
      header: "Lines",
      align: "right" as const,
      render: (row: any) => (
        <span className="text-xs text-text-secondary tabular-nums">
          {row.line_count ?? "—"}
        </span>
      ),
    },
    {
      key: "imports",
      header: "Imports",
      render: (row: any) => (
        <div className="flex flex-wrap gap-1">
          {(row.imports ?? []).map((imp: string) => (
            <span
              key={imp}
              className="rounded bg-bg-elevated px-1.5 py-0.5 text-[11px] text-text-secondary"
            >
              {imp}
            </span>
          ))}
        </div>
      ),
    },
  ];

  return (
    <div className="max-w-5xl">
      <PageHeader
        title="Dependencies"
        description="Module dependency graph and coupling metrics."
      />

      {cycles.length > 0 && (
        <div className="rounded-md border border-error/30 bg-error/5 p-4 mb-6">
          <div className="text-sm font-medium text-error mb-1">
            Circular Dependencies Detected
          </div>
          {cycles.map((cycle: any, i: number) => (
            <div key={i} className="text-xs font-mono text-text-secondary">
              {Array.isArray(cycle) ? cycle.join(" → ") : String(cycle)}
            </div>
          ))}
        </div>
      )}

      {cycles.length === 0 && !isLoading && (
        <div className="mb-6">
          <Badge variant="success">No circular dependencies</Badge>
        </div>
      )}

      <div className="rounded-md border border-border bg-bg-surface">
        {isLoading ? (
          <div className="p-4"><TableSkeleton rows={8} /></div>
        ) : (
          <DataTable columns={columns} data={sorted} keyFn={(r: any) => r.name} />
        )}
      </div>
    </div>
  );
}
```

**Step 2: Add route, commit**

```bash
cd /Users/gunnar/Documents/Dev/nightshift
git add dashboard/src/views/Dependencies.tsx dashboard/src/App.tsx
git commit -m "feat: add Dependencies view with coupling metrics"
```

---

### Task 12: Brain View

**Files:**
- Create: `dashboard/src/views/BrainView.tsx`
- Modify: `dashboard/src/App.tsx` (add route)

**Step 1: Implement Brain page**

```tsx
import { usePlan, useTriage } from "../api/hooks";
import { PageHeader } from "../components/PageHeader";
import { Badge } from "../components/Badge";
import { TableSkeleton } from "../components/Skeleton";

function ScoreBar({ label, value, max = 25 }: { label: string; value: number; max?: number }) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div className="flex items-center gap-2">
      <span className="text-[11px] text-text-tertiary w-24 text-right shrink-0">
        {label}
      </span>
      <div className="flex-1 h-1.5 rounded-full bg-bg-elevated overflow-hidden">
        <div
          className="h-full rounded-full bg-accent"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[11px] font-mono text-text-secondary tabular-nums w-8">
        {value.toFixed(1)}
      </span>
    </div>
  );
}

export function BrainView() {
  const plan = usePlan();
  const triage = useTriage();
  const p = plan.data as any;
  const t = triage.data as any;

  const tasks = p?.top_tasks ?? p?.tasks ?? [];
  const issues = Array.isArray(t) ? t : t?.issues ?? [];

  return (
    <div className="max-w-4xl">
      <PageHeader
        title="Brain"
        description="Task prioritization engine and issue triage."
      />

      <div className="space-y-3 mb-8">
        <div className="text-xs font-medium uppercase tracking-wider text-text-tertiary mb-2">
          Ranked Task Candidates
        </div>
        {plan.isLoading ? (
          <TableSkeleton rows={5} />
        ) : tasks.length === 0 ? (
          <div className="text-sm text-text-tertiary">No task candidates available.</div>
        ) : (
          tasks.map((task: any, i: number) => (
            <div
              key={i}
              className="rounded-md border border-border bg-bg-surface p-4"
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-accent tabular-nums">
                    #{i + 1}
                  </span>
                  <span className="text-[13px] font-medium text-text-primary">
                    {task.title ?? task.name ?? "Untitled"}
                  </span>
                </div>
                <span className="text-sm font-semibold tabular-nums text-text-primary">
                  {task.score != null ? task.score.toFixed(1) : "—"}
                </span>
              </div>
              {task.rationale && (
                <p className="text-xs text-text-secondary mb-3">{task.rationale}</p>
              )}
              {task.breakdown && (
                <div className="space-y-1.5">
                  {task.breakdown.issue_urgency != null && (
                    <ScoreBar label="Urgency" value={task.breakdown.issue_urgency} />
                  )}
                  {task.breakdown.roadmap_alignment != null && (
                    <ScoreBar label="Roadmap" value={task.breakdown.roadmap_alignment} />
                  )}
                  {task.breakdown.health_improvement != null && (
                    <ScoreBar label="Health" value={task.breakdown.health_improvement} />
                  )}
                  {task.breakdown.complexity_fit != null && (
                    <ScoreBar label="Complexity" value={task.breakdown.complexity_fit} />
                  )}
                  {task.breakdown.cross_module_synergy != null && (
                    <ScoreBar label="Synergy" value={task.breakdown.cross_module_synergy} />
                  )}
                </div>
              )}
              {task.source && (
                <div className="mt-2">
                  <Badge variant="neutral">{task.source}</Badge>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {issues.length > 0 && (
        <div>
          <div className="text-xs font-medium uppercase tracking-wider text-text-tertiary mb-2">
            Triaged Issues
          </div>
          <div className="rounded-md border border-border bg-bg-surface divide-y divide-border">
            {issues.map((issue: any, i: number) => (
              <div key={i} className="flex items-center gap-3 px-4 py-3">
                <span className="font-mono text-xs text-text-tertiary">
                  #{issue.number ?? i}
                </span>
                <span className="flex-1 text-[13px] text-text-primary truncate">
                  {issue.title ?? "Untitled"}
                </span>
                {issue.category && (
                  <Badge variant="neutral">{issue.category}</Badge>
                )}
                {issue.priority != null && (
                  <Badge variant={issue.priority <= 2 ? "error" : "neutral"}>
                    P{issue.priority}
                  </Badge>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

**Step 2: Add route, commit**

```bash
cd /Users/gunnar/Documents/Dev/nightshift
git add dashboard/src/views/BrainView.tsx dashboard/src/App.tsx
git commit -m "feat: add Brain view with ranked tasks and score breakdowns"
```

---

### Task 13: Diagnostics View

**Files:**
- Create: `dashboard/src/views/Diagnostics.tsx`
- Modify: `dashboard/src/App.tsx` (add route)

**Step 1: Implement Diagnostics page**

```tsx
import { CircleCheck, AlertTriangle, XCircle } from "lucide-react";
import { useDoctor, useTodos, useScores } from "../api/hooks";
import { PageHeader } from "../components/PageHeader";
import { DataTable } from "../components/DataTable";
import { Badge } from "../components/Badge";
import { TableSkeleton } from "../components/Skeleton";

const STATUS_CONFIG = {
  OK: { icon: CircleCheck, color: "text-success", variant: "success" as const },
  WARN: { icon: AlertTriangle, color: "text-warning", variant: "warning" as const },
  FAIL: { icon: XCircle, color: "text-error", variant: "error" as const },
};

export function Diagnostics() {
  const doctor = useDoctor();
  const todos = useTodos();
  const scores = useScores();

  const doc = doctor.data as any;
  const todoList = Array.isArray(todos.data) ? todos.data : (todos.data as any)?.items ?? [];
  const scoreList = Array.isArray(scores.data) ? scores.data : (scores.data as any)?.scores ?? [];

  const checks = doc?.checks ?? [];

  const todoColumns = [
    {
      key: "file",
      header: "File",
      render: (row: any) => (
        <span className="font-mono text-xs text-text-primary">{row.file ?? row.path ?? "—"}</span>
      ),
    },
    {
      key: "line",
      header: "Line",
      align: "right" as const,
      render: (row: any) => (
        <span className="font-mono text-xs tabular-nums">{row.line ?? "—"}</span>
      ),
    },
    {
      key: "text",
      header: "Annotation",
      render: (row: any) => (
        <span className="text-xs text-text-secondary truncate max-w-xs block">
          {row.text ?? row.content ?? "—"}
        </span>
      ),
    },
    {
      key: "age",
      header: "Age",
      align: "right" as const,
      render: (row: any) => (
        <span className="text-xs text-text-tertiary">
          {row.sessions_old != null ? `${row.sessions_old}s` : "—"}
        </span>
      ),
    },
  ];

  const scoreColumns = [
    {
      key: "pr",
      header: "PR",
      render: (row: any) => (
        <span className="font-mono text-xs text-accent">#{row.pr_number ?? "—"}</span>
      ),
    },
    {
      key: "title",
      header: "Title",
      render: (row: any) => (
        <span className="text-xs text-text-primary truncate max-w-xs block">
          {row.title ?? "—"}
        </span>
      ),
    },
    {
      key: "score",
      header: "Score",
      align: "right" as const,
      render: (row: any) => (
        <span className="font-mono text-xs tabular-nums">{row.total ?? "—"}</span>
      ),
    },
    {
      key: "grade",
      header: "Grade",
      render: (row: any) => {
        const g = row.grade ?? "—";
        const v = g.startsWith("A") ? "success" : g.startsWith("B") ? "warning" : "error";
        return <Badge variant={v as any}>{g}</Badge>;
      },
    },
  ];

  return (
    <div className="max-w-5xl">
      <PageHeader
        title="Diagnostics"
        description="Repo health checks, stale annotations, and PR quality."
      />

      {/* Doctor checks */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-3">
          <span className="text-xs font-medium uppercase tracking-wider text-text-tertiary">
            Doctor
          </span>
          {doc?.grade && <Badge variant="accent">{doc.grade}</Badge>}
        </div>
        {doctor.isLoading ? (
          <TableSkeleton rows={5} />
        ) : (
          <div className="rounded-md border border-border bg-bg-surface divide-y divide-border">
            {checks.map((check: any, i: number) => {
              const cfg = STATUS_CONFIG[check.status as keyof typeof STATUS_CONFIG] ?? STATUS_CONFIG.OK;
              const Icon = cfg.icon;
              return (
                <div key={i} className="flex items-center gap-3 px-4 py-2.5">
                  <Icon size={15} className={cfg.color} />
                  <span className="flex-1 text-[13px] text-text-primary">{check.name}</span>
                  <Badge variant={cfg.variant}>{check.status}</Badge>
                  {check.message && (
                    <span className="text-xs text-text-tertiary max-w-xs truncate">
                      {check.message}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Stale TODOs */}
      {todoList.length > 0 && (
        <div className="mb-8">
          <div className="text-xs font-medium uppercase tracking-wider text-text-tertiary mb-3">
            Stale Annotations
          </div>
          <div className="rounded-md border border-border bg-bg-surface">
            <DataTable columns={todoColumns} data={todoList} keyFn={(r: any) => `${r.file}:${r.line}`} />
          </div>
        </div>
      )}

      {/* PR Scores */}
      {scoreList.length > 0 && (
        <div>
          <div className="text-xs font-medium uppercase tracking-wider text-text-tertiary mb-3">
            PR Quality Scores
          </div>
          <div className="rounded-md border border-border bg-bg-surface">
            <DataTable columns={scoreColumns} data={scoreList} keyFn={(r: any) => `pr-${r.pr_number}`} />
          </div>
        </div>
      )}
    </div>
  );
}
```

**Step 2: Add route, commit**

```bash
cd /Users/gunnar/Documents/Dev/nightshift
git add dashboard/src/views/Diagnostics.tsx dashboard/src/App.tsx
git commit -m "feat: add Diagnostics view with doctor checks, TODOs, PR scores"
```

---

### Task 14: Final App.tsx Wiring + Build Verification

**Files:**
- Modify: `dashboard/src/App.tsx` (ensure all routes registered)

**Step 1: Verify all routes are wired**

Final `App.tsx` should have all imports and routes:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { Overview } from "./views/Overview";
import { Sessions } from "./views/Sessions";
import { Health } from "./views/Health";
import { Coverage } from "./views/Coverage";
import { Dependencies } from "./views/Dependencies";
import { BrainView } from "./views/BrainView";
import { Diagnostics } from "./views/Diagnostics";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchInterval: 30_000,
      staleTime: 10_000,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="flex h-screen">
          <Sidebar />
          <main className="flex-1 overflow-y-auto p-8">
            <Routes>
              <Route path="/" element={<Navigate to="/overview" replace />} />
              <Route path="/overview" element={<Overview />} />
              <Route path="/sessions" element={<Sessions />} />
              <Route path="/health" element={<Health />} />
              <Route path="/coverage" element={<Coverage />} />
              <Route path="/dependencies" element={<Dependencies />} />
              <Route path="/brain" element={<BrainView />} />
              <Route path="/diagnostics" element={<Diagnostics />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
```

**Step 2: Full build check**

Run: `cd /Users/gunnar/Documents/Dev/nightshift/dashboard && npm run build`
Expected: Build succeeds with no errors

**Step 3: Run Python tests**

Run: `cd /Users/gunnar/Documents/Dev/nightshift && python -m pytest tests/ -v`
Expected: All tests pass (existing + new server tests)

**Step 4: Commit**

```bash
cd /Users/gunnar/Documents/Dev/nightshift
git add dashboard/ src/
git commit -m "feat: complete live dashboard with all 7 views"
```

---

### Task 15: Integration Test — End to End

**Step 1: Start the API server in background**

```bash
cd /Users/gunnar/Documents/Dev/nightshift
python -c "from src.server import start_server; start_server(port=8710, open_browser=False)" &
```

**Step 2: Verify API endpoints return JSON**

```bash
curl -s http://127.0.0.1:8710/api/stats | python -m json.tool
curl -s http://127.0.0.1:8710/api/health | python -m json.tool
curl -s http://127.0.0.1:8710/api/doctor | python -m json.tool
```

Expected: Valid JSON from each endpoint

**Step 3: Start Vite dev server and verify**

```bash
cd /Users/gunnar/Documents/Dev/nightshift/dashboard && npm run dev
```

Open `http://localhost:5173` — sidebar should render, data should populate from API.

**Step 4: Kill background server, commit any fixes**

```bash
kill %1
```

**Step 5: Final commit**

```bash
cd /Users/gunnar/Documents/Dev/nightshift
git add -A
git commit -m "chore: integration verification complete"
```
