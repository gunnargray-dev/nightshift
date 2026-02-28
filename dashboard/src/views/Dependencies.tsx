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
          {row.line_count ?? "\u2014"}
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
              {Array.isArray(cycle) ? cycle.join(" \u2192 ") : String(cycle)}
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
