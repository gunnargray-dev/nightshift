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
  if (f.parse_error) return 50;
  let score = 100;
  score -= Math.min((f.long_lines ?? 0) * 0.5, 20);
  score -= Math.min((f.todo_count ?? 0) * 2, 20);
  score -= (1 - (f.docstring_coverage ?? 1)) * 20;
  return Math.max(0, Math.round(score * 10) / 10);
}

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

  const fileList: any[] = Array.isArray(h?.files) ? h.files : [];
  const overallHealth =
    fileList.length > 0
      ? Math.round(fileList.reduce((sum, f) => sum + computeScore(f), 0) / fileList.length)
      : null;

  return (
    <div className="max-w-5xl">
      <PageHeader
        title="Overview"
        description="Real-time snapshot of the awake autonomous development system."
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
              icon={<Clock size={16} />}
            />
            <StatCard
              label="PRs"
              value={s?.total_prs ?? "\u2014"}
              sub="All time"
              icon={<GitPullRequest size={16} />}
            />
            <StatCard
              label="Modules"
              value={s?.total_modules ?? "\u2014"}
              sub="Source files"
              icon={<Blocks size={16} />}
            />
            <StatCard
              label="Tests"
              value={s?.total_tests ?? "\u2014"}
              sub="In test suite"
              icon={<TestTubeDiagonal size={16} />}
            />
            <StatCard
              label="Health"
              value={overallHealth !== null ? `${overallHealth}` : "\u2014"}
              sub={overallHealth !== null ? healthBadge(overallHealth) : ""}
              icon={<TrendingUp size={16} />}
            />
          </>
        )}
      </div>

      {health.isLoading ? (
        <p className="text-sm text-text-muted">Loading health data...</p>
      ) : (
        <div>
          <h2 className="text-sm font-semibold text-text-primary mb-3">Module Health</h2>
          <div className="rounded-lg border border-border overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-bg-elevated border-b border-border">
                  <th className="px-4 py-2.5 text-left font-medium text-text-secondary">Module</th>
                  <th className="px-4 py-2.5 text-right font-medium text-text-secondary">Score</th>
                  <th className="px-4 py-2.5 text-right font-medium text-text-secondary">Long lines</th>
                  <th className="px-4 py-2.5 text-right font-medium text-text-secondary">TODOs</th>
                  <th className="px-4 py-2.5 text-right font-medium text-text-secondary">Docstrings</th>
                  <th className="px-4 py-2.5 text-left font-medium text-text-secondary">Status</th>
                </tr>
              </thead>
              <tbody>
                {fileList.map((f, i) => {
                  const score = computeScore(f);
                  return (
                    <tr
                      key={i}
                      className="border-b border-border last:border-0 hover:bg-bg-elevated/50"
                    >
                      <td className="px-4 py-2.5 font-mono text-xs text-text-primary">{f.file}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums">{score}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums text-text-secondary">{f.long_lines ?? 0}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums text-text-secondary">{f.todo_count ?? 0}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums text-text-secondary">
                        {f.docstring_coverage !== undefined
                          ? `${Math.round(f.docstring_coverage * 100)}%`
                          : "n/a"}
                      </td>
                      <td className="px-4 py-2.5">{healthBadge(score)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
