import type { ApplicationStatus } from "../applications";

const STYLES: Record<ApplicationStatus, string> = {
  draft: "bg-slate-100 text-slate-700",
  submitted: "bg-blue-50 text-blue-700",
  processing: "bg-blue-50 text-blue-700",
  needs_review: "bg-amber-50 text-amber-800",
  clarification_requested: "bg-amber-50 text-amber-800",
  ready_for_decision: "bg-violet-50 text-violet-700",
  approved: "bg-emerald-50 text-emerald-700",
  rejected: "bg-red-50 text-red-700",
};

export default function StatusBadge({ status }: { status: ApplicationStatus }) {
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STYLES[status]}`}>
      {status.replaceAll("_", " ")}
    </span>
  );
}
