import type { Role } from "../api";
import { useAuth } from "../auth";

// What each role will work with; sections get built out from M1 onwards (docs/PLAN.md).
const SECTIONS: Record<Role, { title: string; description: string }[]> = {
  institution: [
    { title: "My applications", description: "Create applications and upload documents." },
    { title: "Deficiencies", description: "Findings that need evidence or clarification." },
    { title: "Alerts", description: "Expiring certificates and upcoming deadlines." },
  ],
  reviewer: [
    { title: "Review queue", description: "Applications and findings awaiting your decision." },
    { title: "Evidence viewer", description: "Each finding linked to its document page and clause." },
    { title: "Alerts", description: "Escalations and overdue institution actions." },
  ],
  admin: [
    { title: "Compliance rules", description: "Versioned rules mapped to APH clauses." },
    { title: "Regulatory sources", description: "Ingested handbooks and circulars." },
    { title: "Users & institutions", description: "Accounts, roles and tenants." },
  ],
};

export default function Dashboard() {
  const { user, logout } = useAuth();
  if (!user) return null;

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <span className="font-semibold text-slate-900">WASP</span>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-slate-600">{user.full_name}</span>
            <span className="rounded bg-slate-100 px-2 py-0.5 text-xs uppercase text-slate-600">
              {user.role}
            </span>
            <button onClick={logout} className="text-slate-500 hover:text-slate-900">
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-8">
        <h1 className="text-xl font-semibold text-slate-900">Dashboard</h1>
        <div className="mt-6 grid gap-4 sm:grid-cols-3">
          {SECTIONS[user.role].map((s) => (
            <section key={s.title} className="rounded-lg border bg-white p-4">
              <h2 className="font-medium text-slate-900">{s.title}</h2>
              <p className="mt-1 text-sm text-slate-500">{s.description}</p>
            </section>
          ))}
        </div>
      </main>
    </div>
  );
}
