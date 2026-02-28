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
          {row.health_score != null ? Math.round(row.health_score) : "\u2014"}
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
