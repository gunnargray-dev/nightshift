import { useHealth } from "../api/hooks";
import { PageHeader } from "../components/PageHeader";
import { DataTable } from "../components/DataTable";
import { Badge } from "../components/Badge";
import { TableSkeleton } from "../components/Skeleton";

/** Compute health score matching Python's FileHealth.health_score property. */
function computeScore(f: any): number {
  if (f.parse_error) return 50;
  let score = 100;
  score -= Math.min((f.long_lines ?? 0) * 0.5, 20);
  score -= Math.min((f.todo_count ?? 0) * 2, 20);
  score -= (1 - (f.docstring_coverage ?? 1)) * 20;
  return Math.max(0, Math.round(score * 10) / 10);
}

function scoreBadge(score: number) {
  if (score >= 90) return <Badge variant="success">Excellent</Badge>;
  if (score >= 80) return <Badge variant="success">Good</Badge>;
  if (score >= 70) return <Badge variant="warning">Fair</Badge>;
  return <Badge variant="error">Needs work</Badge>;
}

export function Health() {
  const { data, isLoading } = useHealth();
  const h = data as any;

  const fileList: any[] = Array.isArray(h?.files) ? h.files : [];
  const scored = fileList.map((f: any) => ({ ...f, health_score: computeScore(f) }));
  const sorted = [...scored].sort((a, b) => b.health_score - a.health_score);
  const overall =
    sorted.length > 0
      ? Math.round(sorted.reduce((s, f) => s + f.health_score, 0) / sorted.length)
      : null;

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
          {Math.round(row.health_score)}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (row: any) => scoreBadge(row.health_score),
    },
    {
      key: "functions",
      header: "Functions",
      align: "right" as const,
      render: (row: any) => (
        <span className="text-xs text-text-secondary tabular-nums">
          {row.function_count ?? "\u2014"}
        </span>
      ),
    },
    {
      key: "lines",
      header: "Lines",
      align: "right" as const,
      render: (row: any) => (
        <span className="text-xs text-text-secondary tabular-nums">
          {row.total_lines ?? "\u2014"}
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
            : "\u2014"}
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

      {overall != null && (
        <div className="flex items-center gap-3 mb-6">
          <span className="text-sm text-text-secondary">Overall:</span>
          <span className="text-lg font-semibold tabular-nums">{overall}</span>
          <span className="text-sm text-text-tertiary">/ 100</span>
          {scoreBadge(overall)}
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
