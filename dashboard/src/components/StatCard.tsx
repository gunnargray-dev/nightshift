import type { ReactNode } from "react";

interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  icon?: ReactNode;
}

export function StatCard({ label, value, sub, icon }: StatCardProps) {
  return (
    <div className="rounded-md border border-border bg-bg-surface p-5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-text-tertiary">
          {label}
        </span>
        {icon && <span className="text-text-tertiary">{icon}</span>}
      </div>
      <div className="mt-2 text-2xl font-semibold tabular-nums text-text-primary">
        {value}
      </div>
      {sub && <div className="mt-0.5 text-xs text-text-tertiary">{sub}</div>}
    </div>
  );
}
