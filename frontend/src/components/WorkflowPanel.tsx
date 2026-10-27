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
import { Button, Notice, Panel, formatDateTime, textareaClass } from "./ui";

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

function useFindings(app: ApplicationDetail, workflow?: Workflow) {
  return useQuery({
    queryKey: ["findings", app.id, workflow?.round ?? 0, app.status],
    queryFn: () => fetchFindings(app.id),
    enabled: app.status !== "draft",
  }).data;
}

/** The clarification request or final decision, shown at the top of the case. */
export function CaseNotice({ app, workflow }: { app: ApplicationDetail; workflow?: Workflow }) {
  const { user } = useAuth();
  const isStaff = user?.role === "reviewer" || user?.role === "admin";
  const findings = useFindings(app, workflow);

  if (app.status === "clarification_requested" && workflow?.clarification) {
    const asked = findings?.filter((f) => workflow.clarification!.finding_ids.includes(f.id)) ?? [];
    return (
      <Notice
        tone="review"
        title={isStaff ? "Waiting for the institution to respond" : "AICTE has asked for a clarification"}
      >
        <p className="whitespace-pre-line">{workflow.clarification.message}</p>
        {asked.length > 0 && (
          <ul className="mt-2 list-disc space-y-0.5 pl-5">
            {asked.map((f) => (
              <li key={f.id}>{f.rule.title}</li>
            ))}
          </ul>
        )}
        {!isStaff && (
          <p className="mt-2">
            Replace or upload the documents below, then resubmit. Only the checks your changes affect will run
            again.
          </p>
        )}
      </Notice>
    );
  }

  if (workflow?.decision) {
    const approved = workflow.decision.decision === "approve";
    return (
      <Notice tone={approved ? "pass" : "fail"} title={`${approved ? "Approved" : "Rejected"}: reviewer's reason`}>
        <p className="whitespace-pre-line">{workflow.decision.reason}</p>
      </Notice>
    );
  }
  return null;
}

/** What happens next on this case, and the reviewer's decision controls. */
export function NextStep({ app, workflow }: { app: ApplicationDetail; workflow?: Workflow }) {
  const { user } = useAuth();
  const isStaff = user?.role === "reviewer" || user?.role === "admin";
  const findings = useFindings(app, workflow);
  const openIds = findings?.filter((f) => OPEN.includes(f.status)).map((f) => f.id) ?? [];

  if (isStaff && workflow?.waiting_for === "reviewer") {
    return <ReviewerActions app={app} workflow={workflow} openFindingIds={openIds} />;
  }

  const waiting: Record<string, string> = {
    extraction: "Reading the documents. Checks run as soon as extraction finishes.",
    reviewer: "An AICTE reviewer is going through the findings.",
    institution: isStaff
      ? "The institution has been asked to respond. You'll be able to act once they resubmit."
      : "Respond to the clarification, then resubmit from this panel.",
  };
  if (workflow?.finished || !workflow?.waiting_for || (!isStaff && workflow.waiting_for === "institution")) {
    return null;
  }
  return (
    <Panel title="Next step">
      <p className="px-5 py-4 text-sm text-muted">{waiting[workflow.waiting_for]}</p>
    </Panel>
  );
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
      ? `Review every open finding first. ${workflow.unreviewed_findings} left.`
      : workflow.confirmed_deficiencies > 0
        ? `${workflow.confirmed_deficiencies} confirmed deficiency. Ask for a clarification or reject.`
        : null;

  const choose = (m: typeof mode) => {
    setMode(mode === m ? null : m);
    setError(null);
  };

  const confirmLabel = { clarify: "Send request", approve: "Approve application", reject: "Reject application" };

  return (
    <Panel title="Your decision">
      <div className="space-y-4 px-5 py-4">
        <p className="text-sm text-muted">
          {openFindingIds.length === 0
            ? "Every check passed."
            : `${openFindingIds.length} open finding${openFindingIds.length === 1 ? "" : "s"}, ${workflow.unreviewed_findings} not yet reviewed.`}
        </p>

        <div className="grid gap-2">
          <Button
            variant="approve"
            onClick={() => choose("approve")}
            disabled={approveBlocked !== null}
            aria-pressed={mode === "approve"}
          >
            Approve…
          </Button>
          {approveBlocked && <p className="text-[13px] text-muted">{approveBlocked}</p>}
          <Button onClick={() => choose("clarify")} disabled={openFindingIds.length === 0} aria-pressed={mode === "clarify"}>
            Request clarification…
          </Button>
          <Button variant="danger" onClick={() => choose("reject")} aria-pressed={mode === "reject"}>
            Reject…
          </Button>
        </div>

        {mode && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              act.mutate();
            }}
            className="space-y-2 border-t pt-4"
          >
            <label className="block">
              <span className="text-sm font-bold">
                {mode === "clarify" ? "What should the institution fix?" : `Reason for ${mode === "approve" ? "approval" : "rejection"}`}
              </span>
              <textarea
                required
                minLength={5}
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={4}
                placeholder={
                  mode === "clarify"
                    ? "All open findings are attached to the request."
                    : "Recorded in the audit trail and shown to the institution."
                }
                className={textareaClass}
              />
            </label>
            {error && <p className="text-sm text-fail">{error}</p>}
            <Button
              type="submit"
              variant={mode === "approve" ? "approve" : mode === "reject" ? "danger" : "primary"}
              disabled={act.isPending}
              className="w-full"
            >
              {confirmLabel[mode]}
            </Button>
          </form>
        )}
      </div>
    </Panel>
  );
}

const EVENT_LABELS: Record<string, (e: WorkflowEvent) => string> = {
  application_created: () => "Draft created",
  application_submitted: () => "Submitted for review",
  application_resubmitted: () => "Resubmitted after clarification",
  application_evaluated: (e) => {
    const to = humanize(String(e.to_status)).toLowerCase();
    if (e.payload.round === undefined) return `Compliance checks run; ${to}`; // pre-workflow events
    const rechecked = (e.payload.rechecked as string[]) ?? [];
    const carried = Number(e.payload.carried_over ?? 0);
    return `Round ${e.payload.round} checks: ${rechecked.length} rule${rechecked.length === 1 ? "" : "s"} run${
      carried ? `, ${carried} carried over` : ""
    }; ${to}`;
  },
  evaluation_requested: () => "Checks re-run on request",
  finding_reviewed: (e) =>
    `${e.payload.outcome === "override" ? "Overrode" : "Confirmed"} a finding${e.payload.comment ? `: “${e.payload.comment}”` : ""}`,
  clarification_requested: (e) => `Asked for a clarification: “${e.payload.message}”`,
  alert_raised: (e) => `Alert raised: ${e.payload.title}`,
  alert_overdue: (e) => `Alert overdue: ${e.payload.title}`,
  alert_escalated: (e) => `Alert escalated: ${e.payload.title}`,
  alert_reopened: (e) => `Alert reopened: ${e.payload.title}`,
  alert_acknowledged: (e) => `Alert acknowledged: ${e.payload.title}`,
  alert_resolved: (e) =>
    e.payload.automatic === false
      ? `Alert resolved by a reviewer: “${e.payload.note}”`
      : `Alert resolved automatically: ${e.payload.title}`,
  application_decided: (e) => `${e.payload.decision === "approve" ? "Approved" : "Rejected"}: “${e.payload.reason}”`,
};

const DOCUMENT_EVENTS: Record<string, string> = {
  document_uploaded: "uploaded",
  compliance_document_updated: "renewed",
  document_processed: "read",
  document_reprocess_requested: "queued to be read again",
  document_deleted: "deleted",
};

const MILESTONES = new Set(["application_submitted", "application_resubmitted", "clarification_requested", "application_decided"]);

/** Audit trail. Runs of document events collapse into one entry so decisions stay readable. */
export function Timeline({ workflow }: { workflow: Workflow }) {
  type Row = { label: string; actor: string | null; at: string; milestone: boolean };
  const rows: Row[] = [];
  let run: { counts: Record<string, number>; actor: string | null; at: string } | null = null;

  const flush = () => {
    if (!run) return;
    const parts = Object.entries(run.counts).map(([verb, n]) => `${n} ${verb}`);
    rows.push({ label: `Documents: ${parts.join(", ")}`, actor: run.actor, at: run.at, milestone: false });
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
    rows.push({ label, actor: e.actor, at: e.created_at, milestone: MILESTONES.has(e.event_type) });
  }
  flush();

  return (
    <Panel title="Audit trail">
      <ol className="px-5 py-4">
        {rows.map((r, i) => (
          <li key={i} className="relative flex gap-4 pb-4 last:pb-0">
            {i < rows.length - 1 && <span className="absolute top-3 bottom-0 left-[5px] w-px bg-rule" aria-hidden />}
            <span
              className={`relative mt-1.5 size-[11px] shrink-0 rounded-full border-2 ${
                r.milestone ? "border-stamp bg-stamp" : "border-rule-strong bg-sheet"
              }`}
              aria-hidden
            />
            <div className="min-w-0 flex-1 sm:flex sm:gap-4">
              <p className={`flex-1 text-[15px] ${r.milestone ? "font-bold" : ""}`}>
                {r.label}
                {r.actor && <span className="font-normal text-muted">, {r.actor}</span>}
              </p>
              <time className="shrink-0 text-sm text-faint" dateTime={r.at}>
                {formatDateTime(r.at)}
              </time>
            </div>
          </li>
        ))}
      </ol>
    </Panel>
  );
}
