import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  decideApplication,
  fetchFindings,
  humanize,
  requestClarification,
  type ApplicationDetail,
  type Workflow,
  type WorkflowEvent,
} from "../applications";
import { useAuth } from "../auth";

const OPEN = ["fail", "needs_review", "unable_to_determine"];

export function useInvalidateCase(applicationId: string) {
  const queryClient = useQueryClient();
  return () => {
    for (const key of ["application", "findings", "workflow"]) {
      queryClient.invalidateQueries({ queryKey: [key, applicationId] });
    }
    queryClient.invalidateQueries({ queryKey: ["applications"] });
  };
}

/** Status banner (clarification / decision) plus the reviewer's case actions. */
export function CaseBanner({ app, workflow }: { app: ApplicationDetail; workflow?: Workflow }) {
  const { user } = useAuth();
  const isStaff = user?.role === "reviewer" || user?.role === "admin";
  const { data: findings } = useQuery({
    queryKey: ["findings", app.id, workflow?.round ?? 0, app.status],
    queryFn: () => fetchFindings(app.id),
    enabled: app.status !== "draft",
  });

  if (app.status === "clarification_requested" && workflow?.clarification) {
    const asked = findings?.filter((f) => workflow.clarification!.finding_ids.includes(f.id)) ?? [];
    return (
      <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950">
        <div className="font-medium">
          {isStaff ? "Clarification requested — waiting for the institution" : "AICTE has requested a clarification"}
        </div>
        <p className="mt-1 whitespace-pre-line">{workflow.clarification.message}</p>
        {asked.length > 0 && (
          <ul className="mt-2 list-inside list-disc text-xs">
            {asked.map((f) => (
              <li key={f.id}>
                <b>{f.rule.title}</b>: {f.reason}
              </li>
            ))}
          </ul>
        )}
        {!isStaff && (
          <p className="mt-2 text-xs">
            Upload or replace the documents below, then click <b>Resubmit</b>. Only the checks
            affected by your changes will be re-run.
          </p>
        )}
      </div>
    );
  }

  if (workflow?.decision) {
    const approved = workflow.decision.decision === "approve";
    return (
      <div
        className={`mt-4 rounded-lg border px-4 py-3 text-sm ${
          approved ? "border-emerald-300 bg-emerald-50 text-emerald-950" : "border-red-300 bg-red-50 text-red-950"
        }`}
      >
        <div className="font-medium">
          {approved ? "Approved" : "Rejected"} on {new Date(workflow.decision.decided_at).toLocaleString()}
        </div>
        <p className="mt-1 whitespace-pre-line">{workflow.decision.reason}</p>
      </div>
    );
  }

  if (isStaff && workflow?.waiting_for === "reviewer") {
    return <ReviewerActions app={app} workflow={workflow} openFindingIds={findings?.filter((f) => OPEN.includes(f.status)).map((f) => f.id) ?? []} />;
  }
  return null;
}

function ReviewerActions({
  app,
  workflow,
  openFindingIds,
}: {
  app: ApplicationDetail;
  workflow: Workflow;
  openFindingIds: string[];
}) {
  const invalidate = useInvalidateCase(app.id);
  const [mode, setMode] = useState<"clarify" | "approve" | "reject" | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);

  const act = useMutation({
    mutationFn: () => {
      if (mode === "clarify") return requestClarification(app.id, text, openFindingIds);
      return decideApplication(app.id, mode === "approve" ? "approve" : "reject", text);
    },
    onSuccess: () => {
      setMode(null);
      setText("");
      setTimeout(invalidate, 800);
    },
    onError: (e) => setError(e.message),
  });

  const approveBlocked =
    workflow.unreviewed_findings > 0
      ? `Review all open findings first (${workflow.unreviewed_findings} remaining).`
      : workflow.confirmed_deficiencies > 0
        ? `${workflow.confirmed_deficiencies} confirmed deficiency(ies): request clarification or reject.`
        : null;

  const button = (m: typeof mode, label: string, style: string, disabled = false) => (
    <button
      onClick={() => {
        setMode(mode === m ? null : m);
        setError(null);
      }}
      disabled={disabled}
      className={`rounded-md px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-40 ${style}`}
    >
      {label}
    </button>
  );

  return (
    <div className="mt-4 rounded-lg border bg-white px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-slate-700">
          <span className="font-medium text-slate-900">Your review.</span>{" "}
          {openFindingIds.length === 0
            ? "All checks passed."
            : `${openFindingIds.length} open finding(s); ${workflow.unreviewed_findings} not yet reviewed.`}
        </div>
        <div className="flex flex-wrap gap-2">
          {button("clarify", "Request clarification…", "border text-slate-800 hover:bg-slate-50", openFindingIds.length === 0)}
          {button("reject", "Reject…", "border border-red-300 text-red-700 hover:bg-red-50")}
          {button("approve", "Approve…", "bg-emerald-700 text-white hover:bg-emerald-800", approveBlocked !== null)}
        </div>
      </div>
      {approveBlocked && <p className="mt-2 text-xs text-slate-500">Approve: {approveBlocked}</p>}

      {mode && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            act.mutate();
          }}
          className="mt-3 space-y-2"
        >
          <textarea
            required
            minLength={5}
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
            placeholder={
              mode === "clarify"
                ? "What should the institution provide or correct? All open findings are attached."
                : `Reason for ${mode === "approve" ? "approval" : "rejection"} (recorded in the audit trail)`
            }
            className="w-full rounded-md border px-3 py-2 text-sm"
          />
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button
            disabled={act.isPending}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            {mode === "clarify" ? "Send request" : mode === "approve" ? "Confirm approval" : "Confirm rejection"}
          </button>
        </form>
      )}
    </div>
  );
}

const EVENT_LABELS: Record<string, (e: WorkflowEvent) => string> = {
  application_created: () => "Draft created",
  application_submitted: () => "Submitted for review",
  application_resubmitted: () => "Resubmitted after clarification",
  application_evaluated: (e) => {
    const to = humanize(String(e.to_status));
    if (e.payload.round === undefined) return `Compliance checks run → ${to}`;  // pre-workflow events
    const rechecked = (e.payload.rechecked as string[]) ?? [];
    const carried = Number(e.payload.carried_over ?? 0);
    return `Round ${e.payload.round}: re-checked ${rechecked.length} rule(s)${carried ? `, ${carried} unchanged` : ""} → ${to}`;
  },
  evaluation_requested: () => "Requested re-evaluation",
  finding_reviewed: (e) => `${e.payload.outcome === "override" ? "Overrode" : "Confirmed"} a finding${e.payload.comment ? `: “${e.payload.comment}”` : ""}`,
  clarification_requested: (e) => `Requested clarification: “${e.payload.message}”`,
  application_decided: (e) => `${e.payload.decision === "approve" ? "Approved" : "Rejected"}: “${e.payload.reason}”`,
};

const DOCUMENT_EVENTS: Record<string, string> = {
  document_uploaded: "uploaded",
  document_processed: "extracted",
  document_reprocess_requested: "queued for re-extraction",
  document_deleted: "deleted",
};

/** Audit timeline. Runs of document events collapse into one line so decisions stay readable. */
export function Timeline({ workflow }: { workflow: Workflow }) {
  type Row = { label: string; actor: string | null; at: string };
  const rows: Row[] = [];
  let run: { counts: Record<string, number>; actor: string | null; at: string } | null = null;

  const flush = () => {
    if (!run) return;
    const parts = Object.entries(run.counts).map(([verb, n]) => `${n} ${verb}`);
    const total = Object.values(run.counts).reduce((a, b) => a + b, 0);
    rows.push({
      label: total === 1 && run.counts.uploaded ? "1 document uploaded" : `Documents: ${parts.join(", ")}`,
      actor: run.actor,
      at: run.at,
    });
    run = null;
  };

  for (const e of workflow.events) {
    const verb = DOCUMENT_EVENTS[e.event_type];
    if (verb) {
      run ??= { counts: {}, actor: e.actor, at: e.created_at };
      run.counts[verb] = (run.counts[verb] ?? 0) + 1;
      run.actor ??= e.actor;
      continue;
    }
    flush();
    const label = EVENT_LABELS[e.event_type]?.(e) ?? humanize(e.event_type);
    rows.push({ label, actor: e.actor, at: e.created_at });
  }
  flush();

  return (
    <section className="mt-6 rounded-lg border bg-white">
      <h2 className="border-b px-4 py-3 text-sm font-medium text-slate-900">Audit trail</h2>
      <ol className="space-y-2 px-4 py-3">
        {rows.map((r, i) => (
          <li key={i} className="flex gap-3 text-sm">
            <span className="w-36 shrink-0 text-xs tabular-nums text-slate-400">
              {new Date(r.at).toLocaleString()}
            </span>
            <span className="text-slate-700">
              {r.label}
              {r.actor && <span className="text-slate-400"> · {r.actor}</span>}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
