import type { ReactNode } from "react";
import { Link, NavLink } from "react-router";
import { useAuth } from "../auth";

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  if (!user) return null;

  const navLink = ({ isActive }: { isActive: boolean }) =>
    isActive ? "text-slate-900 font-medium" : "text-slate-500 hover:text-slate-900";

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-center gap-6 text-sm">
            <Link to="/" className="text-base font-semibold text-slate-900">
              WASP
            </Link>
            <NavLink to="/applications" className={navLink}>
              {user.role === "institution" ? "My applications" : "Review queue"}
            </NavLink>
            {user.role !== "institution" && (
              <>
                <NavLink to="/rules" className={navLink}>
                  Rules
                </NavLink>
                <NavLink to="/handbook" className={navLink}>
                  Handbook
                </NavLink>
              </>
            )}
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="hidden text-slate-600 sm:inline">{user.full_name}</span>
            <span className="rounded bg-slate-100 px-2 py-0.5 text-xs uppercase text-slate-600">
              {user.role}
            </span>
            <button onClick={logout} className="text-slate-500 hover:text-slate-900">
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
    </div>
  );
}
