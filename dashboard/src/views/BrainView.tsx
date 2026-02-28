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
                  {task.score != null ? task.score.toFixed(1) : "\u2014"}
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
