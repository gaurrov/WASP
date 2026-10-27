import { Link } from "react-router";
import type { Role } from "../api";
import { useAuth } from "../auth";
import Layout from "../components/Layout";

interface Section {
  title: string;
  description: string;
  to?: string;
  milestone?: string; // shown until the section is built (see docs/PLAN.md)
}

const SECTIONS: Record<Role, Section[]> = {
  institution: [
    { title: "My applications", description: "Create applications and upload documents.", to: "/applications" },
    { title: "Compliance check", description: "See what each submitted application is missing.", to: "/applications" },
    { title: "Alerts", description: "Expiring certificates and response deadlines.", to: "/alerts" },
  ],
  reviewer: [
    { title: "Review queue", description: "Submitted applications and their document checklists.", to: "/applications" },
    { title: "Compliance rules", description: "Rules, their norms and handbook verification.", to: "/rules" },
    { title: "Alerts", description: "Escalations, overdue responses and review SLAs.", to: "/alerts" },
  ],
  admin: [
    { title: "All applications", description: "Every application across institutions.", to: "/applications" },
    { title: "Compliance rules", description: "Verify rules against handbook clauses.", to: "/rules" },
    { title: "Regulatory handbook", description: "Upload and search official sources.", to: "/handbook" },
  ],
};

export default function Dashboard() {
  const { user } = useAuth();
  if (!user) return null;

  return (
    <Layout>
      <h1 className="text-xl font-semibold text-slate-900">Dashboard</h1>
      <div className="mt-6 grid gap-4 sm:grid-cols-3">
        {SECTIONS[user.role].map((s) => {
          const body = (
            <>
              <div className="flex items-center justify-between">
                <h2 className="font-medium text-slate-900">{s.title}</h2>
                {s.milestone && (
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500">
                    {s.milestone}
                  </span>
                )}
              </div>
              <p className="mt-1 text-sm text-slate-500">{s.description}</p>
            </>
          );
          return s.to ? (
            <Link key={s.title} to={s.to} className="rounded-lg border bg-white p-4 hover:border-slate-400">
              {body}
            </Link>
          ) : (
            <section key={s.title} className="rounded-lg border bg-white p-4 opacity-60">
              {body}
            </section>
          );
        })}
      </div>
    </Layout>
  );
}
