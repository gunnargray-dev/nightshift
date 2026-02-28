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
        <span className="font-mono text-xs text-text-primary">{row.file ?? row.path ?? "\u2014"}</span>
      ),
    },
    {
      key: "line",
      header: "Line",
      align: "right" as const,
      render: (row: any) => (
        <span className="font-mono text-xs tabular-nums">{row.line ?? "\u2014"}</span>
      ),
    },
    {
      key: "text",
      header: "Annotation",
      render: (row: any) => (
        <span className="text-xs text-text-secondary truncate max-w-xs block">
          {row.text ?? row.content ?? "\u2014"}
        </span>
      ),
    },
    {
      key: "age",
      header: "Age",
      align: "right" as const,
      render: (row: any) => (
        <span className="text-xs text-text-tertiary">
          {row.sessions_old != null ? `${row.sessions_old}s` : "\u2014"}
        </span>
      ),
    },
  ];

  const scoreColumns = [
    {
      key: "pr",
      header: "PR",
      render: (row: any) => (
        <span className="font-mono text-xs text-accent">#{row.pr_number ?? "\u2014"}</span>
      ),
    },
    {
      key: "title",
      header: "Title",
      render: (row: any) => (
        <span className="text-xs text-text-primary truncate max-w-xs block">
          {row.title ?? "\u2014"}
        </span>
      ),
    },
    {
      key: "score",
      header: "Score",
      align: "right" as const,
      render: (row: any) => (
        <span className="font-mono text-xs tabular-nums">{row.total ?? "\u2014"}</span>
      ),
    },
    {
      key: "grade",
      header: "Grade",
      render: (row: any) => {
        const g = row.grade ?? "\u2014";
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
