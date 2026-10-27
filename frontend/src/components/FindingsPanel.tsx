import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import {
  fetchFindings,
  humanize,
  reevaluate,
  type ApplicationDetail,
  type Finding,
  type FindingStatus,
  type Workflow,
  reviewFinding,
} from "../applications";
import { useAuth } from "../auth";
import { useInvalidateCase } from "./WorkflowPanel";

const OPEN_STATUSES: FindingStatus[] = ["fail", "needs_review", "unable_to_determine"];

const STATUS: Record<FindingStatus, { label: string; style: string; icon: string }> = {
  fail: { label: "Fail", style: "bg-red-50 text-red-700 border-red-200", icon: "✕" },
  needs_review: { label: "Needs review", style: "bg-amber-50 text-amber-900 border-amber-200", icon: "!" },
  unable_to_determine: { label: "Can't determine", style: "bg-slate-100 text-slate-700 border-slate-200", icon: "?" },
  pass: { label: "Pass", style: "bg-emerald-50 text-emerald-700 border-emerald-200", icon: "✓" },
  not_applicable: { label: "N/A", style: "bg-slate-50 text-slate-500 border-slate-200", icon: "–" },
};

function formatValue(value: unknown): string {
  if (value && typeof value === "object") return Object.values(value).join(" · ");
  return String(value);
}

export default function FindingsPanel({
  app,
  workflow,
}: {
  app: ApplicationDetail;
  workflow?: Workflow;
}) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const isStaff = user?.role === "reviewer" || user?.role === "admin";
  const evaluating = app.status === "submitted" || app.status === "processing";

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
    <section className="mt-6 rounded-lg border bg-white">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-sm font-medium text-slate-900">
            {user?.role === "institution" ? "Compliance check" : "Findings"}
          </h2>
          {(["fail", "needs_review", "unable_to_determine", "pass"] as FindingStatus[]).map(
            (s) =>
              counts[s] ? (
                <span key={s} className={`rounded-full border px-2 py-0.5 text-xs ${STATUS[s].style}`}>
                  {counts[s]} {STATUS[s].label.toLowerCase()}
                </span>
              ) : null,
          )}
        </div>
        {isStaff && workflow?.waiting_for === "reviewer" && (
          <button
            onClick={() => rerun.mutate()}
            disabled={rerun.isPending || evaluating}
            className="rounded-md border px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Re-evaluate
          </button>
        )}
      </div>
      {workflow && workflow.round > 1 && (
        <p className="border-b bg-slate-50 px-4 py-2 text-xs text-slate-600">
          Round {workflow.round}: re-checked {workflow.rechecked.length} of {workflow.total_rules}{" "}
          rules affected by the changed documents ({workflow.rechecked.join(", ")}); the rest
          carried over unchanged.
        </p>
      )}

      {evaluating && (!findings || findings.length === 0) ? (
        <p className="px-4 py-6 text-sm text-slate-500">Running compliance checks…</p>
      ) : findings && findings.length > 0 ? (
        <ul className="divide-y">
          {findings.map((f) => (
            <FindingRow
              key={f.id}
              finding={f}
              canReview={isStaff && workflow?.waiting_for === "reviewer"}
              applicationId={app.id}
            />
          ))}
        </ul>
      ) : (
        <p className="px-4 py-6 text-sm text-slate-500">No findings yet.</p>
      )}
    </section>
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
  const expiring = f.details.expiring_soon === true;

  return (
    <li className="px-4 py-3">
      <button onClick={() => setOpen(!open)} className="flex w-full items-start gap-3 text-left">
        <span
          className={`mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border text-xs ${s.style}`}
        >
          {s.icon}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-sm font-medium text-slate-900">{f.rule.title}</span>
            <span className="text-xs text-slate-400">
              {f.rule.code} v{f.rule.version} · {f.severity}
            </span>
            {f.provisional && (
              <span
                title={f.rule.norm_note ?? undefined}
                className="rounded border border-dashed border-amber-400 px-1.5 text-[11px] text-amber-800"
              >
                provisional — rule not yet verified against APH
              </span>
            )}
            {expiring && (
              <span className="rounded bg-amber-100 px-1.5 text-[11px] text-amber-900">
                expiring soon
              </span>
            )}
            {f.review && (
              <span
                title={f.review.comment ?? undefined}
                className={`rounded px-1.5 text-[11px] ${
                  f.review.outcome === "override" ? "bg-violet-50 text-violet-700" : "bg-slate-100 text-slate-700"
                }`}
              >
                {f.review.outcome === "override" ? "overridden" : "confirmed"} by {f.review.reviewer}
              </span>
            )}
          </div>
          <p className="mt-0.5 text-sm text-slate-600">{f.reason}</p>
        </div>
      </button>

      {open && (f.evidence.length > 0 || f.citations.length > 0 || f.provisional || canReview) && (
        <div className="mt-3 space-y-3 pl-8">
          {f.evidence.length > 0 && (
            <div>
              <div className="text-xs font-medium text-slate-500">Evidence</div>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {f.evidence.map((e) => (
                  <Link
                    key={e.fact_id}
                    to={`/documents/${e.document_id}?fact=${e.fact_id}`}
                    className={`rounded border px-2 py-1 text-xs hover:border-slate-400 ${
                      e.low_confidence ? "border-amber-300 bg-amber-50" : "bg-slate-50"
                    }`}
                  >
                    <span className="text-slate-500">{e.filename}</span>{" "}
                    <span className="text-slate-400">· {humanize(e.field_name)}:</span>{" "}
                    <span className="text-slate-900">{formatValue(e.value)}</span>
                    {e.low_confidence && (
                      <span className="ml-1 text-amber-800">({Math.round(e.confidence * 100)}%)</span>
                    )}
                  </Link>
                ))}
              </div>
            </div>
          )}

          {f.citations.length > 0 && (
            <div>
              <div className="text-xs font-medium text-slate-500">
                {f.citations.some((c) => c.verified) ? "Regulation" : "Possibly relevant handbook passages (unverified)"}
              </div>
              <div className="mt-1 space-y-2">
                {f.citations.map((c) => (
                  <blockquote
                    key={c.chunk_id}
                    className={`rounded border-l-4 bg-slate-50 px-3 py-2 text-xs text-slate-700 ${
                      c.verified ? "border-blue-500" : "border-slate-300"
                    }`}
                  >
                    <div className="mb-1 font-medium text-slate-900">
                      {c.source_title} {c.source_version}
                      {c.section && ` · § ${c.section}`}
                      {c.heading && ` ${c.heading}`}
                      {c.page && ` · p. ${c.page}`}
                      {c.verified && <span className="ml-2 text-blue-700">verified clause</span>}
                    </div>
                    <p className="line-clamp-4 whitespace-pre-line">{c.text}</p>
                  </blockquote>
                ))}
              </div>
            </div>
          )}

          {f.review?.comment && (
            <p className="text-xs text-slate-600">
              <span className="font-medium">Reviewer:</span> {f.review.comment}
            </p>
          )}
          {canReview && OPEN_STATUSES.includes(f.status) && (
            <ReviewControls findingId={f.id} applicationId={applicationId} />
          )}

          {f.provisional && f.rule.norm_note && (
            <p className="text-xs text-slate-500">
              <span className="font-medium">Where this norm comes from:</span> {f.rule.norm_note}
            </p>
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
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-dashed px-3 py-2">
      <input
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="Comment (required to override)"
        className="min-w-48 flex-1 rounded border px-2 py-1 text-xs"
      />
      <button
        onClick={() => review.mutate("confirm")}
        disabled={review.isPending}
        className="rounded border px-2 py-1 text-xs text-slate-800 hover:bg-slate-50"
      >
        Confirm deficiency
      </button>
      <button
        onClick={() => review.mutate("override")}
        disabled={review.isPending || comment.trim().length < 5}
        className="rounded border border-violet-300 px-2 py-1 text-xs text-violet-800 hover:bg-violet-50 disabled:opacity-40"
      >
        Override
      </button>
      {review.error && <span className="text-xs text-red-600">{review.error.message}</span>}
    </div>
  );
}
