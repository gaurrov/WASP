import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { acknowledgeAlert, resolveAlert, type Alert } from "../applications";
import { useAuth } from "../auth";
import { Button, Pill, buttonClass, formatDate, inputClass, type Tone } from "./ui";

const SEVERITY: Record<string, { mark: string; label: string }> = {
  critical: { mark: "bg-fail", label: "Critical" },
  high: { mark: "bg-[#c2410c]", label: "High" },
  medium: { mark: "bg-review", label: "Medium" },
  low: { mark: "bg-[#5b7fb5]", label: "Low" },
  info: { mark: "bg-faint", label: "Info" },
};

const STATUS: Record<string, { label: string; tone: Tone }> = {
  active: { label: "Open", tone: "info" },
  reopened: { label: "Reopened", tone: "info" },
  acknowledged: { label: "Acknowledged", tone: "neutral" },
  overdue: { label: "Overdue", tone: "review" },
  escalated: { label: "Escalated", tone: "fail" },
  resolved: { label: "Resolved", tone: "pass" },
};

const OPEN = ["active", "acknowledged", "overdue", "escalated", "reopened"];

/**
 * An alert. "card" is the full version for the alert centre; "row" is a compact line for
 * the overview and case file, where the context (institution, application) is already known.
 */
export default function AlertCard({ alert, variant = "card" }: { alert: Alert; variant?: "card" | "row" }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [resolving, setResolving] = useState(false);
  const [note, setNote] = useState("");
  const isStaff = user?.role === "reviewer" || user?.role === "admin";
  const open = OPEN.includes(alert.status);
  const severity = SEVERITY[alert.severity] ?? SEVERITY.info;
  const status = STATUS[alert.status] ?? { label: alert.status, tone: "neutral" as Tone };

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

  const renewal = alert.alert_type === "certificate_expiry" && alert.application_id && !isStaff && open;

  if (variant === "row") {
    return (
      <div className="flex items-start gap-3 px-5 py-3.5">
        <span className={`mt-2 size-2 shrink-0 rounded-full ${severity.mark}`} aria-label={severity.label} />
        <div className="min-w-0 flex-1">
          <p className="font-bold">{alert.title}</p>
          <p className="text-sm text-muted">
            {alert.institution_name}
            {alert.due_at && <>, due {formatDate(alert.due_at)}</>}
          </p>
        </div>
        <Pill tone={status.tone}>{status.label}</Pill>
        {renewal && (
          <Link to={`/applications/${alert.application_id}`} className={buttonClass("primary", "sm")}>
            Upload renewal
          </Link>
        )}
      </div>
    );
  }

  return (
    <article className="relative overflow-hidden rounded-[var(--radius-panel)] border bg-sheet">
      <span className={`absolute inset-y-0 left-0 w-1 ${severity.mark}`} aria-hidden />
      <div className="py-4 pr-5 pl-6">
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
          <div className="min-w-0">
            <h3 className="font-bold">{alert.title}</h3>
            <p className="mt-0.5 text-sm text-muted">
              {alert.institution_name}
              {alert.application_id && (
                <>
                  {", "}
                  <Link to={`/applications/${alert.application_id}`} className="underline-offset-2 hover:underline">
                    {alert.application_label}
                  </Link>
                </>
              )}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {alert.audience === "reviewer" && <Pill tone="stamp">For reviewers</Pill>}
            <Pill tone={status.tone}>{status.label}</Pill>
          </div>
        </div>

        <p className="mt-2 max-w-3xl text-[15px]">{alert.message}</p>

        <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <div className="flex gap-1.5">
            <dt className="text-muted">Severity</dt>
            <dd className="font-bold">{severity.label}</dd>
          </div>
          {alert.due_at && (
            <div className="flex gap-1.5">
              <dt className="text-muted">Due</dt>
              <dd className="font-bold">{formatDate(alert.due_at)}</dd>
            </div>
          )}
          <div className="flex gap-1.5">
            <dt className="text-muted">Raised</dt>
            <dd>{formatDate(alert.created_at)}</dd>
          </div>
        </dl>

        {alert.resolution_note && (
          <p className="mt-3 border-l-2 border-pass pl-3 text-sm text-pass">
            Resolved {formatDate(alert.resolved_at)}: {alert.resolution_note}
          </p>
        )}

        {open && (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {renewal && (
              <Link to={`/applications/${alert.application_id}`} className={buttonClass("primary", "sm")}>
                Upload renewal
              </Link>
            )}
            {alert.status !== "acknowledged" && !alert.acknowledged_at && (
              <Button size="sm" onClick={() => ack.mutate()} disabled={ack.isPending}>
                Acknowledge
              </Button>
            )}
            {isStaff && !resolving && (
              <Button size="sm" variant="ghost" onClick={() => setResolving(true)}>
                Resolve with a note
              </Button>
            )}
          </div>
        )}
        {resolving && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              resolve.mutate();
            }}
            className="mt-3 flex max-w-2xl flex-wrap items-end gap-2"
          >
            <label className="min-w-64 flex-1">
              <span className="sr-only">Resolution note</span>
              <input
                autoFocus
                required
                minLength={5}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="What happened instead, e.g. renewal verified with the fire department"
                className={inputClass.replace("mt-1.5", "")}
              />
            </label>
            <Button type="submit" variant="primary">
              Resolve alert
            </Button>
            <Button type="button" variant="ghost" onClick={() => setResolving(false)}>
              Cancel
            </Button>
          </form>
        )}
      </div>
    </article>
  );
}
