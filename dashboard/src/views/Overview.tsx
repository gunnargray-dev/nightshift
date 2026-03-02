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
              icon={<Clock size={15} />}
            />
            <StatCard
              label="PRs"
              value={s?.prs_merged ?? "\u2014"}
              sub="Merged"
              icon={<GitPullRequest size={15} />}
            />
            <StatCard
              label="Features"
              value={s?.features_shipped ?? "\u2014"}
              sub="Shipped"
              icon={<Blocks size={15} />}
            />
            <StatCard
              label="Tests"
              value={s?.tests_added ?? "\u2014"}
              sub="Added"
              icon={<TestTubeDiagonal size={15} />}
            />
            <StatCard
              label="Health"
              value={overallHealth !== null ? `${overallHealth}%` : "\u2014"}
              sub="Code quality"
              icon={<TrendingUp size={15} />}
            />
          </>
        )}
      </div>

      {health.isLoading ? (
        <div className="text-sm text-gray-500">Loading health data...</div>
      ) : (
        <div className="border border-gray-800 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 bg-gray-900">
                <th className="text-left px-4 py-2 text-gray-400 font-medium">File</th>
                <th className="text-left px-4 py-2 text-gray-400 font-medium">Score</th>
                <th className="text-left px-4 py-2 text-gray-400 font-medium">Status</th>
                <th className="text-left px-4 py-2 text-gray-400 font-medium">Issues</th>
              </tr>
            </thead>
            <tbody>
              {fileList.map((f, i) => {
                const score = computeScore(f);
                return (
                  <tr
                    key={i}
                    className="border-b border-gray-800 last:border-0 hover:bg-gray-900/50"
                  >
                    <td className="px-4 py-2 font-mono text-xs text-gray-300">{f.file}</td>
                    <td className="px-4 py-2 text-gray-300">{score}%</td>
                    <td className="px-4 py-2">{healthBadge(score)}</td>
                    <td className="px-4 py-2 text-gray-500 text-xs">
                      {[
                        f.long_lines ? `${f.long_lines} long lines` : null,
                        f.todo_count ? `${f.todo_count} TODOs` : null,
                        f.parse_error ? "parse error" : null,
                      ]
                        .filter(Boolean)
                        .join(", ") || "None"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
