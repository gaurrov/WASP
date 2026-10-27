import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, CircleCheck, CircleHelp, CircleX, FileText, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import {
  fetchFindings,
  humanize,
  reevaluate,
  reviewFinding,
  type ApplicationDetail,
  type Finding,
  type FindingStatus,
  type Workflow,
} from "../applications";
import { useAuth } from "../auth";
import { Button, Panel, Pill, formatValue, inputClass, type Tone } from "./ui";
import { useInvalidateCase } from "./WorkflowPanel";

const OPEN_STATUSES: FindingStatus[] = ["fail", "needs_review", "unable_to_determine"];

const STATUS: Record<FindingStatus, { label: string; tone: Tone; icon: typeof CircleX; color: string }> = {
  fail: { label: "failed", tone: "fail", icon: CircleX, color: "text-fail" },
  needs_review: { label: "need review", tone: "review", icon: TriangleAlert, color: "text-review" },
  unable_to_determine: { label: "undetermined", tone: "neutral", icon: CircleHelp, color: "text-muted" },
  pass: { label: "passed", tone: "pass", icon: CircleCheck, color: "text-pass" },
  not_applicable: { label: "not applicable", tone: "neutral", icon: CircleHelp, color: "text-faint" },
};

export default function FindingsPanel({ app, workflow }: { app: ApplicationDetail; workflow?: Workflow }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const isStaff = user?.role === "reviewer" || user?.role === "admin";
  const evaluating = app.status === "submitted" || app.status === "processing";
  const canReview = isStaff && workflow?.waiting_for === "reviewer";

  const { data: findings } = useQuery({
    // A new evaluation round or status change means new findings.
    queryKey: ["findings", app.id, workflow?.round ?? 0, app.status],
    queryFn: () => fetchFindings(app.id),
    refetchInterval: evaluating ? 2000 : false,
  });

  const rerun = useMutation({
    mutationFn: () => reevaluate(app.id),
    onSuccess: () => {
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ["findings", app.id] });
        queryClient.invalidateQueries({ queryKey: ["application", app.id] });
      }, 1500);
    },
  });

  const counts = (findings ?? []).reduce<Partial<Record<FindingStatus, number>>>(
    (acc, f) => ({ ...acc, [f.status]: (acc[f.status] ?? 0) + 1 }),
    {},
  );

  return (
    <Panel
      title={user?.role === "institution" ? "Compliance check" : "Findings"}
      actions={
        <div className="flex flex-wrap items-center gap-2">
          {(["fail", "needs_review", "unable_to_determine", "pass"] as FindingStatus[]).map((s) =>
            counts[s] ? (
              <Pill key={s} tone={STATUS[s].tone}>
                {counts[s]} {STATUS[s].label}
              </Pill>
            ) : null,
          )}
          {canReview && (
            <Button size="sm" variant="ghost" onClick={() => rerun.mutate()} disabled={rerun.isPending || evaluating}>
              Re-run checks
            </Button>
          )}
        </div>
      }
    >
      {workflow && workflow.round > 1 && (
        <p className="border-b bg-stamp-soft/60 px-5 py-2.5 text-sm">
          <span className="font-bold">Round {workflow.round}.</span> Re-checked {workflow.rechecked.length} of{" "}
          {workflow.total_rules} rules affected by the changed documents ({workflow.rechecked.join(", ")}). The
          others are carried over unchanged.
        </p>
      )}

      {evaluating && (!findings || findings.length === 0) ? (
        <p className="px-5 py-8 text-muted">Running compliance checks…</p>
      ) : findings && findings.length > 0 ? (
        <ul className="divide-y">
          {findings.map((f) => (
            <FindingRow key={f.id} finding={f} canReview={canReview} applicationId={app.id} />
          ))}
        </ul>
      ) : (
        <p className="px-5 py-8 text-muted">Checks run when the application is submitted.</p>
      )}
    </Panel>
  );
}

function FindingRow({
  finding: f,
  canReview,
  applicationId,
}: {
  finding: Finding;
  canReview: boolean;
  applicationId: string;
}) {
  const [open, setOpen] = useState(f.status !== "pass");
  const s = STATUS[f.status];
  const Icon = s.icon;
  const hasBody = f.evidence.length > 0 || f.citations.length > 0 || f.provisional || canReview || !!f.review;

  return (
    <li>
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        disabled={!hasBody}
        className="flex w-full items-start gap-3 px-5 py-4 text-left transition-colors enabled:hover:bg-paper/60"
      >
        <Icon size={20} strokeWidth={2} className={`mt-0.5 shrink-0 ${s.color}`} aria-label={s.label} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
            <span className="font-bold">{f.rule.title}</span>
            {f.provisional && (
              <span
                title={f.rule.norm_note ?? undefined}
                className="rounded-full border border-dashed border-review/60 px-2 py-0.5 text-xs text-review"
              >
                Provisional
              </span>
            )}
            {f.details.expiring_soon === true && <Pill tone="review">Expiring soon</Pill>}
            {f.review && (
              <Pill tone={f.review.outcome === "override" ? "stamp" : "neutral"}>
                {f.review.outcome === "override" ? "Overridden" : "Confirmed"} by {f.review.reviewer}
              </Pill>
            )}
          </div>
          <p className="mt-1 text-[15px] text-ink/80">{f.reason}</p>
        </div>
        <span className="hidden shrink-0 pt-0.5 text-xs text-faint sm:block">{f.rule.code}</span>
        {hasBody && (
          <ChevronDown
            size={18}
            className={`mt-0.5 shrink-0 text-faint transition-transform ${open ? "rotate-180" : ""}`}
            aria-hidden
          />
        )}
      </button>

      {open && hasBody && (
        <div className="space-y-4 pr-5 pb-5 pl-[3.25rem]">
          {f.evidence.length > 0 && (
            <div>
              <h4 className="text-sm text-muted">Evidence</h4>
              <ul className="mt-1.5 flex flex-wrap gap-2">
                {f.evidence.map((e) => (
                  <li key={e.fact_id}>
                    <Link
                      to={`/documents/${e.document_id}?fact=${e.fact_id}`}
                      className={`inline-flex items-center gap-1.5 rounded-[var(--radius-control)] border px-2.5 py-1.5 text-sm transition-colors hover:border-stamp ${
                        e.low_confidence ? "border-review/40 bg-review-soft" : "bg-paper"
                      }`}
                    >
                      <FileText size={14} className="text-faint" aria-hidden />
                      <span className="text-muted">{humanize(e.field_name)}:</span>
                      <span className="font-bold">{formatValue(e.value)}</span>
                      {e.low_confidence && (
                        <span className="text-review">{Math.round(e.confidence * 100)}% sure</span>
                      )}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {f.citations.length > 0 && (
            <div>
              <h4 className="text-sm text-muted">
                {f.citations.some((c) => c.verified) ? "Regulation" : "Possibly relevant handbook passages, not yet verified"}
              </h4>
              <div className="mt-1.5 space-y-2">
                {f.citations.map((c) => (
                  <blockquote
                    key={c.chunk_id}
                    className={`border-l-[3px] bg-paper/70 py-2 pr-3 pl-4 text-sm ${c.verified ? "border-stamp" : "border-rule-strong"}`}
                  >
                    <p className="font-bold">
                      {c.source_title} {c.source_version}
                      {c.section && `, §${c.section}`}
                      {c.heading && ` ${c.heading}`}
                      {c.page && `, page ${c.page}`}
                    </p>
                    <p className="mt-1 line-clamp-4 whitespace-pre-line text-ink/80">{c.text}</p>
                  </blockquote>
                ))}
              </div>
            </div>
          )}

          {f.provisional && f.rule.norm_note && (
            <p className="text-sm text-muted">
              <span className="font-bold text-ink">Where this norm comes from.</span> {f.rule.norm_note}
            </p>
          )}

          {f.review?.comment && (
            <p className="border-l-[3px] border-stamp pl-4 text-sm">
              <span className="font-bold">{f.review.reviewer}:</span> {f.review.comment}
            </p>
          )}

          {canReview && OPEN_STATUSES.includes(f.status) && (
            <ReviewControls findingId={f.id} applicationId={applicationId} />
          )}
        </div>
      )}
    </li>
  );
}

function ReviewControls({ findingId, applicationId }: { findingId: string; applicationId: string }) {
  const invalidate = useInvalidateCase(applicationId);
  const [comment, setComment] = useState("");
  const review = useMutation({
    mutationFn: (outcome: "confirm" | "override") => reviewFinding(findingId, outcome, comment || undefined),
    onSuccess: () => {
      setComment("");
      invalidate();
    },
  });
  return (
    <div className="flex flex-wrap items-end gap-2 rounded-[var(--radius-control)] border border-dashed border-rule-strong p-3">
      <label className="min-w-56 flex-1">
        <span className="text-sm font-bold">Your review</span>
        <input
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Reason (required to override)"
          className={inputClass}
        />
      </label>
      <Button onClick={() => review.mutate("confirm")} disabled={review.isPending}>
        Confirm deficiency
      </Button>
      <Button
        variant="primary"
        onClick={() => review.mutate("override")}
        disabled={review.isPending || comment.trim().length < 5}
      >
        Override
      </Button>
      {review.error && <p className="w-full text-sm text-fail">{review.error.message}</p>}
    </div>
  );
}
