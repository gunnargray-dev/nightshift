import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Clock,
  HeartPulse,
  TestTubeDiagonal,
  GitFork,
  Brain,
  Stethoscope,
} from "lucide-react";

const NAV_ITEMS = [
  { to: "/overview", label: "Overview", icon: LayoutDashboard },
  { to: "/sessions", label: "Sessions", icon: Clock },
  { to: "/health", label: "Health", icon: HeartPulse },
  { to: "/coverage", label: "Coverage", icon: TestTubeDiagonal },
  { to: "/dependencies", label: "Dependencies", icon: GitFork },
  { to: "/brain", label: "Brain", icon: Brain },
  { to: "/diagnostics", label: "Diagnostics", icon: Stethoscope },
];

export function Sidebar() {
  return (
    <aside className="w-52 shrink-0 border-r border-border bg-bg-surface flex flex-col">
      <div className="px-4 py-5">
        <span className="text-sm font-semibold tracking-tight text-text-primary">
          awake
        </span>
      </div>
      <nav className="flex-1 px-2 space-y-0.5">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] font-medium transition-colors ${
                isActive
                  ? "bg-accent/10 text-accent"
                  : "text-text-secondary hover:text-text-primary hover:bg-bg-elevated"
              }`
            }
          >
            <Icon size={16} strokeWidth={1.75} />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
