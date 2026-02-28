import {
  Clock,
  GitPullRequest,
  Blocks,
  TestTubeDiagonal,
  TrendingUp,
} from "lucide-react";
import { useStats, useHealth } from "../api/hooks";
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
              value={s?.nights_active ?? "\u2014"}
              sub="Nights active"
              icon={<Clock size={15} />}
            />
            <StatCard
              label="PRs"
              value={s?.total_prs ?? "\u2014"}
              sub="Merged"
              icon={<GitPullRequest size={15} />}
            />
            <StatCard
              label="Modules"
              value={h?.files ? Object.keys(h.files).length : "\u2014"}
              sub="in src/"
              icon={<Blocks size={15} />}
            />
            <StatCard
              label="Tests"
              value={s?.total_commits ?? "\u2014"}
              sub="Total commits"
              icon={<TestTubeDiagonal size={15} />}
            />
            <StatCard
              label="Health"
              value={h?.overall_health_score != null ? `${Math.round(h.overall_health_score)}` : "\u2014"}
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
                    {session.date ?? "\u2014"} {"\u2014"} {session.prs ?? 0} PRs
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
