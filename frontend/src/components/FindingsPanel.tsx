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
} from "../applications";
import { useAuth } from "../auth";

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

export default function FindingsPanel({ app }: { app: ApplicationDetail }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const isStaff = user?.role === "reviewer" || user?.role === "admin";
  const evaluating = app.status === "submitted" || app.status === "processing";

  const { data: findings } = useQuery({
    queryKey: ["findings", app.id],
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
        {isStaff && (
          <button
            onClick={() => rerun.mutate()}
            disabled={rerun.isPending || evaluating}
            className="rounded-md border px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Re-evaluate
          </button>
        )}
      </div>

      {evaluating && (!findings || findings.length === 0) ? (
        <p className="px-4 py-6 text-sm text-slate-500">Running compliance checks…</p>
      ) : findings && findings.length > 0 ? (
        <ul className="divide-y">
          {findings.map((f) => (
            <FindingRow key={f.id} finding={f} />
          ))}
        </ul>
      ) : (
        <p className="px-4 py-6 text-sm text-slate-500">No findings yet.</p>
      )}
    </section>
  );
}

function FindingRow({ finding: f }: { finding: Finding }) {
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
          </div>
          <p className="mt-0.5 text-sm text-slate-600">{f.reason}</p>
        </div>
      </button>

      {open && (f.evidence.length > 0 || f.citations.length > 0 || f.provisional) && (
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
