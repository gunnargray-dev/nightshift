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
                    {s.date ?? "\u2014"}
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
