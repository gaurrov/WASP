import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { Link } from "react-router";
import {
  fetchAlerts,
  fetchApplications,
  fetchRules,
  type ApplicationStatus,
  type ApplicationSummary,
} from "../applications";
import { useAuth } from "../auth";
import AlertCard from "../components/AlertCard";
import Layout from "../components/Layout";
import {
  EmptyState,
  PageHeader,
  Panel,
  StatusPill,
  buttonClass,
  formatDate,
} from "../components/ui";

const STAGES: { label: string; statuses: ApplicationStatus[] }[] = [
  { label: "Needs review", statuses: ["needs_review", "submitted", "processing"] },
  { label: "Ready for decision", statuses: ["ready_for_decision"] },
  { label: "With the institution", statuses: ["clarification_requested"] },
  { label: "Decided", statuses: ["approved", "rejected"] },
];

/** What the institution should do next, in plain words. */
export const NEXT_STEP: Record<ApplicationStatus, string> = {
  draft: "Upload documents and submit",
  submitted: "Being checked",
  processing: "Being checked",
  needs_review: "With an AICTE reviewer",
  ready_for_decision: "Awaiting decision",
  clarification_requested: "Respond to the clarification request",
  approved: "Approved; keep certificates current",
  rejected: "Rejected; see the reviewer's reason",
};

export default function Dashboard() {
  const { user } = useAuth();
  const isStaff = user?.role === "reviewer" || user?.role === "admin";
  const { data: apps = [] } = useQuery({ queryKey: ["applications"], queryFn: fetchApplications });
  const { data: alerts = [] } = useQuery({
    queryKey: ["alerts", "open"],
    queryFn: () => fetchAlerts({ status: "open" }),
  });
  const { data: rules = [] } = useQuery({ queryKey: ["rules"], queryFn: fetchRules, enabled: isStaff });
  if (!user) return null;

  const draftRules = rules.filter((r) => !r.internal && r.status !== "approved").length;
  const actionable = isStaff
    ? apps
        .filter((a) => a.status === "needs_review" || a.status === "ready_for_decision")
        .sort((a, b) => (a.submitted_at ?? "").localeCompare(b.submitted_at ?? ""))
    : apps;

  return (
    <Layout>
      <PageHeader
        title={isStaff ? "Overview" : `Welcome, ${user.full_name}`}
        description={
          isStaff
            ? "Cases waiting for a decision, and compliance obligations falling due."
            : "Your applications and anything that needs your attention."
        }
        actions={
          !isStaff && (
            <Link to="/applications/new" className={buttonClass("primary")}>
              New application
            </Link>
          )
        }
      />

      {isStaff && (
        <dl className="mb-8 grid grid-cols-2 overflow-hidden rounded-[var(--radius-panel)] border bg-sheet sm:grid-cols-4">
          {STAGES.map((s, i) => (
            <div
              key={s.label}
              className={`px-5 py-4 ${i % 2 ? "border-l" : ""} ${i > 1 ? "max-sm:border-t sm:border-l" : ""}`}
            >
              <dt className="text-sm text-muted">{s.label}</dt>
              <dd className="mt-1 text-[1.75rem] leading-none font-bold">
                {apps.filter((a) => s.statuses.includes(a.status)).length}
              </dd>
            </div>
          ))}
        </dl>
      )}

      <div className="grid items-start gap-8 lg:grid-cols-[1.45fr_1fr]">
        <Panel
          title={isStaff ? "Needs your action" : "Your applications"}
          actions={
            <Link to="/applications" className="text-sm text-muted hover:text-ink">
              View all
            </Link>
          }
        >
          <CaseList
            apps={actionable}
            showNextStep={!isStaff}
            empty={isStaff ? "Nothing is waiting for review." : "You haven't started an application yet."}
          />
        </Panel>

        <div className="space-y-8">
          <Panel
            title="Open alerts"
            actions={
              <Link to="/alerts" className="text-sm text-muted hover:text-ink">
                View all
              </Link>
            }
          >
            {alerts.length === 0 ? (
              <p className="px-5 py-5 text-sm text-muted">
                No open alerts. Certificates and deadlines are checked every hour.
              </p>
            ) : (
              <div className="divide-y">
                {alerts.slice(0, 3).map((a) => (
                  <AlertCard key={a.id} alert={a} variant="row" />
                ))}
              </div>
            )}
          </Panel>

          {isStaff && draftRules > 0 && (
            <Panel title="Rules awaiting verification">
              <div className="px-5 py-4 text-sm">
                <p>
                  {draftRules} regulatory rule{draftRules === 1 ? " uses a norm" : "s use norms"} not yet
                  checked against the handbook, so {draftRules === 1 ? "its" : "their"} findings are
                  marked provisional.
                </p>
                <Link to="/rules" className={`${buttonClass("secondary", "sm")} mt-3`}>
                  Verify rules
                </Link>
              </div>
            </Panel>
          )}
        </div>
      </div>
    </Layout>
  );
}

function CaseList({
  apps,
  showNextStep,
  empty,
}: {
  apps: ApplicationSummary[];
  showNextStep: boolean;
  empty: string;
}) {
  if (apps.length === 0) {
    return (
      <div className="p-5">
        <EmptyState title={empty} />
      </div>
    );
  }
  return (
    <ul className="divide-y">
      {apps.slice(0, 8).map((a) => (
        <li key={a.id}>
          <Link
            to={`/applications/${a.id}`}
            className="flex items-center gap-4 px-5 py-3.5 transition-colors hover:bg-paper/70"
          >
            <div className="min-w-0 flex-1">
              <p className="truncate font-bold">{a.institution_name}</p>
              <p className="truncate text-sm text-muted">
                {a.application_type_label} {a.academic_year}
                <span className="mx-2 text-rule-strong" aria-hidden>
                  |
                </span>
                {showNextStep ? NEXT_STEP[a.status] : `Submitted ${formatDate(a.submitted_at)}`}
              </p>
            </div>
            <StatusPill status={a.status} />
            <ChevronRight size={16} className="shrink-0 text-faint" aria-hidden />
          </Link>
        </li>
      ))}
    </ul>
  );
}
