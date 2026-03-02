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

function computeScore(f: any): number {
  if (!f) return 0;
  const pass = f.passed ?? 0;
  const fail = f.failed ?? 0;
  const skip = f.skipped ?? 0;
  const total = pass + fail + skip;
  if (total === 0) return 0;
  return Math.round((pass / total) * 100);
}

function scoreVariant(
  score: number
): "success" | "warning" | "danger" | "neutral" {
  if (score >= 90) return "success";
  if (score >= 70) return "warning";
  if (score >= 1) return "danger";
  return "neutral";
}

export function Overview() {
  const { data: stats, isLoading: statsLoading } = useStats();
  const { data: health } = useHealth();

  const testScore = computeScore(stats?.tests);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Overview"
        subtitle="Summary of your repository health and recent activity."
      />

      {health && (
        <div className="flex items-center gap-2 text-sm">
          <span className="text-zinc-400">Status:</span>
          <Badge
            variant={
              health.status === "ok"
                ? "success"
                : health.status === "degraded"
                ? "warning"
                : "danger"
            }
          >
            {health.status}
          </Badge>
          {health.version && (
            <span className="text-zinc-500 text-xs">v{health.version}</span>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {statsLoading ? (
          Array.from({ length: 5 }).map((_, i) => <StatCardSkeleton key={i} />)
        ) : (
          <>
            <StatCard
              title="Open PRs"
              value={stats?.prs?.open ?? 0}
              icon={<GitPullRequest className="w-5 h-5" />}
              variant="default"
            />
            <StatCard
              title="Modules"
              value={stats?.modules ?? 0}
              icon={<Blocks className="w-5 h-5" />}
              variant="default"
            />
            <StatCard
              title="Test Score"
              value={`${testScore}%`}
              icon={<TestTubeDiagonal className="w-5 h-5" />}
              variant={scoreVariant(testScore)}
            />
            <StatCard
              title="Avg Complexity"
              value={
                stats?.complexity?.average !== undefined
                  ? stats.complexity.average.toFixed(1)
                  : "N/A"
              }
              icon={<TrendingUp className="w-5 h-5" />}
              variant="default"
            />
            <StatCard
              title="Last Run"
              value={
                stats?.last_run
                  ? new Date(stats.last_run).toLocaleString()
                  : "N/A"
              }
              icon={<Clock className="w-5 h-5" />}
              variant="default"
            />
          </>
        )}
      </div>
    </div>
  );
}
