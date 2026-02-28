const VARIANTS = {
  success: "bg-success/15 text-success",
  warning: "bg-warning/15 text-warning",
  error: "bg-error/15 text-error",
  neutral: "bg-bg-elevated text-text-secondary",
  accent: "bg-accent/15 text-accent",
} as const;

interface BadgeProps {
  variant: keyof typeof VARIANTS;
  children: React.ReactNode;
}

export function Badge({ variant, children }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-semibold ${VARIANTS[variant]}`}
    >
      {children}
    </span>
  );
}
