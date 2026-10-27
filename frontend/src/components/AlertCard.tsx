import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { acknowledgeAlert, resolveAlert, type Alert } from "../applications";
import { useAuth } from "../auth";

const SEVERITY_BAR: Record<string, string> = {
  critical: "bg-red-600",
  high: "bg-orange-500",
  medium: "bg-amber-400",
  low: "bg-sky-400",
  info: "bg-slate-300",
};

const STATUS_STYLE: Record<string, string> = {
  active: "bg-blue-50 text-blue-700",
  reopened: "bg-blue-50 text-blue-700",
  acknowledged: "bg-slate-100 text-slate-700",
  overdue: "bg-orange-50 text-orange-800",
  escalated: "bg-red-50 text-red-700",
  resolved: "bg-emerald-50 text-emerald-700",
};

const OPEN = ["active", "acknowledged", "overdue", "escalated", "reopened"];

export default function AlertCard({ alert, compact = false }: { alert: Alert; compact?: boolean }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [resolving, setResolving] = useState(false);
  const [note, setNote] = useState("");
  const isStaff = user?.role === "reviewer" || user?.role === "admin";
  const open = OPEN.includes(alert.status);

  const refresh = () => {
    for (const key of ["alerts", "alert-summary"]) queryClient.invalidateQueries({ queryKey: [key] });
  };
  const ack = useMutation({ mutationFn: () => acknowledgeAlert(alert.id), onSuccess: refresh });
  const resolve = useMutation({
    mutationFn: () => resolveAlert(alert.id, note),
    onSuccess: () => {
      setResolving(false);
      refresh();
    },
  });

  return (
    <div className="flex overflow-hidden rounded-lg border bg-white">
      <div className={`w-1.5 shrink-0 ${SEVERITY_BAR[alert.severity]}`} />
      <div className="min-w-0 flex-1 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-slate-900">{alert.title}</span>
          <span className={`rounded px-1.5 py-0.5 text-[11px] ${STATUS_STYLE[alert.status] ?? ""}`}>
            {alert.status}
          </span>
          <span className="text-[11px] uppercase tracking-wide text-slate-400">{alert.severity}</span>
          {alert.audience === "reviewer" && (
            <span className="rounded bg-violet-50 px-1.5 py-0.5 text-[11px] text-violet-700">for reviewers</span>
          )}
        </div>
        {!compact && (
          <div className="mt-0.5 text-xs text-slate-500">
            {alert.institution_name}
            {alert.application_id && (
              <>
                {" · "}
                <Link to={`/applications/${alert.application_id}`} className="underline">
                  {alert.application_label}
                </Link>
              </>
            )}
            {alert.due_at && ` · due ${new Date(alert.due_at).toLocaleDateString()}`}
          </div>
        )}
        <p className="mt-1 whitespace-pre-line text-sm text-slate-600">{alert.message}</p>
        {alert.resolution_note && (
          <p className="mt-1 text-xs text-emerald-700">
            Resolved{alert.resolved_at && ` ${new Date(alert.resolved_at).toLocaleDateString()}`}: {alert.resolution_note}
          </p>
        )}

        {open && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {alert.status !== "acknowledged" && !alert.acknowledged_at && (
              <button
                onClick={() => ack.mutate()}
                disabled={ack.isPending}
                className="rounded border px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
              >
                Acknowledge
              </button>
            )}
            {alert.alert_type === "certificate_expiry" && alert.application_id && !isStaff && (
              <Link
                to={`/applications/${alert.application_id}`}
                className="rounded bg-slate-900 px-2 py-1 text-xs text-white"
              >
                Upload renewal
              </Link>
            )}
            {isStaff && !resolving && (
              <button
                onClick={() => setResolving(true)}
                className="rounded border px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
              >
                Resolve with note…
              </button>
            )}
            {resolving && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  resolve.mutate();
                }}
                className="flex flex-1 flex-wrap gap-2"
              >
                <input
                  autoFocus
                  required
                  minLength={5}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Alternative outcome, e.g. renewal verified with the fire department"
                  className="min-w-56 flex-1 rounded border px-2 py-1 text-xs"
                />
                <button className="rounded bg-slate-900 px-2 py-1 text-xs text-white">Resolve</button>
              </form>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
