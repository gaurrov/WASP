import { useQuery } from "@tanstack/react-query";
import { BellRing, BookOpen, FolderOpen, LayoutGrid, LogOut, Scale } from "lucide-react";
import type { ReactNode } from "react";
import { Link, NavLink } from "react-router";
import { fetchAlertSummary } from "../applications";
import { useAuth } from "../auth";

const ROLE_LABEL = { institution: "Institution", reviewer: "AICTE reviewer", admin: "Administrator" };

/** WASP mark: a case-file seal. */
export function Mark({ className = "size-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <circle cx="16" cy="16" r="14.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="16" cy="16" r="11" fill="none" stroke="currentColor" strokeWidth="1" strokeDasharray="1.5 2" />
      <path
        d="M9.5 12.5 12 21l4-6.5 4 6.5 2.5-8.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const { data: summary } = useQuery({
    queryKey: ["alert-summary"],
    queryFn: fetchAlertSummary,
    enabled: !!user,
    refetchInterval: 30_000,
  });
  if (!user) return null;

  const isStaff = user.role !== "institution";
  const items = [
    { to: "/", label: "Overview", icon: LayoutGrid, end: true },
    { to: "/applications", label: isStaff ? "Review queue" : "Applications", icon: FolderOpen },
    { to: "/alerts", label: "Alerts", icon: BellRing, count: summary?.open, urgent: !!summary?.critical },
    ...(isStaff
      ? [
          { to: "/rules", label: "Rules", icon: Scale },
          { to: "/handbook", label: "Handbook", icon: BookOpen },
        ]
      : []),
  ];

  const navLink = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 rounded-[var(--radius-control)] px-3 py-2 text-[15px] transition-colors ${
      isActive
        ? "bg-sheet font-bold text-ink shadow-[0_0_0_1px_var(--color-rule)]"
        : "text-muted hover:bg-sheet/70 hover:text-ink"
    }`;

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[15rem_1fr]">
      <aside className="border-b bg-paper lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col lg:border-r lg:border-b-0">
        <Link to="/" className="flex items-center gap-3 px-5 py-4 lg:py-6">
          <Mark className="size-9 text-stamp" />
          <span className="leading-tight">
            <span className="block text-lg font-extrabold tracking-[0.04em]">WASP</span>
            <span className="block text-xs text-muted">AICTE approvals</span>
          </span>
        </Link>

        <nav
          aria-label="Main"
          className="flex gap-1 overflow-x-auto px-3 pb-3 [scrollbar-width:none] lg:flex-1 lg:flex-col lg:overflow-visible lg:pb-0"
        >
          {items.map(({ to, label, icon: Icon, end, count, urgent }) => (
            <NavLink key={to} to={to} end={end} className={navLink}>
              <Icon size={18} strokeWidth={1.75} aria-hidden />
              <span className="flex-1 whitespace-nowrap">{label}</span>
              {!!count && (
                <span
                  className={`rounded-full px-1.5 text-xs leading-5 font-bold text-white ${urgent ? "bg-fail" : "bg-review"}`}
                  aria-label={`${count} open`}
                >
                  {count}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="hidden border-t px-5 py-4 lg:block">
          <p className="truncate text-sm font-bold">{user.full_name}</p>
          <p className="text-xs text-muted">{ROLE_LABEL[user.role]}</p>
          <button onClick={logout} className="mt-3 inline-flex items-center gap-2 text-sm text-muted hover:text-ink">
            <LogOut size={15} aria-hidden />
            Sign out
          </button>
        </div>
      </aside>

      <div className="min-w-0">
        <div className="flex items-center justify-end gap-3 border-b bg-sheet px-5 py-2 text-sm lg:hidden">
          <span className="text-muted">{user.full_name}</span>
          <button onClick={logout} className="text-muted hover:text-ink">
            Sign out
          </button>
        </div>
        <main className="mx-auto w-full max-w-[76rem] px-5 py-8 sm:px-8 lg:py-10">{children}</main>
      </div>
    </div>
  );
}
