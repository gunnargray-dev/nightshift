export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded bg-bg-elevated ${className}`}
    />
  );
}

export function StatCardSkeleton() {
  return (
    <div className="rounded-md border border-border bg-bg-surface p-5">
      <Skeleton className="h-3 w-16 mb-3" />
      <Skeleton className="h-7 w-20 mb-1" />
      <Skeleton className="h-3 w-24" />
    </div>
  );
}

export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-8 w-full" />
      ))}
    </div>
  );
}
