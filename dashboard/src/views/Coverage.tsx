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
          S{row.session ?? "\u2014"}
        </span>
      ),
    },
    {
      key: "coverage",
      header: "Coverage",
      align: "right" as const,
      render: (row: any) => (
        <span className="font-mono text-xs tabular-nums">
          {row.total_coverage != null ? `${row.total_coverage.toFixed(1)}%` : "\u2014"}
        </span>
      ),
    },
    {
      key: "lines",
      header: "Covered / Total",
      align: "right" as const,
      render: (row: any) => (
        <span className="text-xs text-text-secondary tabular-nums">
          {row.lines_covered ?? "\u2014"} / {row.lines_total ?? "\u2014"}
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
