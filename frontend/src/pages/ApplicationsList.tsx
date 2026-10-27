import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { fetchApplications, type ApplicationStatus } from "../applications";
import { useAuth } from "../auth";
import Layout from "../components/Layout";
import {
  EmptyState,
  ErrorText,
  PageHeader,
  StatusPill,
  buttonClass,
  caseRef,
  formatDate,
} from "../components/ui";
import { NEXT_STEP } from "./Dashboard";

const FILTERS: { key: string; label: string; statuses?: ApplicationStatus[] }[] = [
  { key: "all", label: "All" },
  { key: "review", label: "Needs review", statuses: ["submitted", "processing", "needs_review", "ready_for_decision"] },
  { key: "clarification", label: "With institution", statuses: ["clarification_requested"] },
  { key: "decided", label: "Decided", statuses: ["approved", "rejected"] },
];

export default function ApplicationsList() {
  const { user } = useAuth();
  const isInstitution = user?.role === "institution";
  const [filter, setFilter] = useState("all");
  const { data: apps, isLoading, error } = useQuery({
    queryKey: ["applications"],
    queryFn: fetchApplications,
  });

  const statuses = FILTERS.find((f) => f.key === filter)?.statuses;
  const shown = (apps ?? []).filter((a) => !statuses || statuses.includes(a.status));

  return (
    <Layout>
      <PageHeader
        title={isInstitution ? "Applications" : "Review queue"}
        description={
          isInstitution
            ? "Applications you've drafted or submitted to AICTE."
            : "Submitted applications across institutions. Drafts aren't shown until submitted."
        }
        actions={
          isInstitution && (
            <Link to="/applications/new" className={buttonClass("primary")}>
              New application
            </Link>
          )
        }
      />

      {!isInstitution && (
        <div role="tablist" aria-label="Filter by stage" className="mb-4 flex flex-wrap gap-1">
          {FILTERS.map((f) => {
            const count = (apps ?? []).filter((a) => !f.statuses || f.statuses.includes(a.status)).length;
            return (
              <button
                key={f.key}
                role="tab"
                aria-selected={filter === f.key}
                onClick={() => setFilter(f.key)}
                className={`rounded-full px-3.5 py-1.5 text-sm transition-colors ${
                  filter === f.key ? "bg-ink text-white" : "text-muted hover:bg-sheet hover:text-ink"
                }`}
              >
                {f.label} <span className="opacity-70">{count}</span>
              </button>
            );
          })}
        </div>
      )}

      {error && <ErrorText>{error.message}</ErrorText>}
      {isLoading && <p className="text-muted">Loading applications…</p>}
      {apps && shown.length === 0 && (
        <EmptyState
          title={isInstitution ? "No applications yet" : "Nothing in this stage"}
          body={
            isInstitution
              ? "Start an application, upload your documents, and submit it when the checklist is complete."
              : "Applications appear here once an institution submits them."
          }
          action={
            isInstitution && (
              <Link to="/applications/new" className={buttonClass("primary")}>
                New application
              </Link>
            )
          }
        />
      )}

      {shown.length > 0 && (
        <div className="overflow-x-auto rounded-[var(--radius-panel)] border bg-sheet">
          <table className="w-full text-left">
            <thead className="border-b text-sm text-muted">
              <tr>
                {!isInstitution && <th className="px-5 py-3 font-normal">Institution</th>}
                <th className="px-5 py-3 font-normal">Application</th>
                <th className="px-5 py-3 font-normal">Reference</th>
                <th className="px-5 py-3 font-normal">Documents</th>
                <th className="px-5 py-3 font-normal">{isInstitution ? "Next step" : "Submitted"}</th>
                <th className="px-5 py-3 font-normal">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {shown.map((a) => (
                <tr key={a.id} className="group transition-colors hover:bg-paper/70">
                  {!isInstitution && (
                    <td className="px-5 py-3.5 font-bold">
                      <Link to={`/applications/${a.id}`} className="hover:underline">
                        {a.institution_name}
                      </Link>
                    </td>
                  )}
                  <td className="px-5 py-3.5">
                    <Link to={`/applications/${a.id}`} className={isInstitution ? "font-bold hover:underline" : ""}>
                      {a.application_type_label} {a.academic_year}
                    </Link>
                  </td>
                  <td className="px-5 py-3.5 text-sm text-muted">{caseRef(a)}</td>
                  <td className="px-5 py-3.5 text-sm">{a.document_count}</td>
                  <td className="px-5 py-3.5 text-sm text-muted">
                    {isInstitution ? NEXT_STEP[a.status] : formatDate(a.submitted_at)}
                  </td>
                  <td className="px-5 py-3.5">
                    <StatusPill status={a.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Layout>
  );
}
