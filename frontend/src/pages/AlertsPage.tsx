import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fetchAlerts, runMonitoringScan } from "../applications";
import { useAuth } from "../auth";
import AlertCard from "../components/AlertCard";
import Layout from "../components/Layout";
import { Button, EmptyState, PageHeader, inputClass } from "../components/ui";

type Filter = "open" | "resolved" | "all";
const FILTERS: { key: Filter; label: string }[] = [
  { key: "open", label: "Open" },
  { key: "resolved", label: "Resolved" },
  { key: "all", label: "All" },
];

export default function AlertsPage() {
  const { user } = useAuth();
  const [filter, setFilter] = useState<Filter>("open");
  const { data: alerts, isLoading } = useQuery({
    queryKey: ["alerts", filter],
    queryFn: () => fetchAlerts({ status: filter }),
    refetchInterval: 30_000,
  });

  return (
    <Layout>
      <PageHeader
        title="Alerts"
        description="Expiring certificates, response deadlines and overdue reviews. An alert closes by itself once the documents show the obligation is met."
      />

      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div role="tablist" aria-label="Filter alerts" className="flex gap-1">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              role="tab"
              aria-selected={filter === f.key}
              onClick={() => setFilter(f.key)}
              className={`rounded-full px-3.5 py-1.5 text-sm transition-colors ${
                filter === f.key ? "bg-ink text-white" : "text-muted hover:bg-sheet hover:text-ink"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        {user?.role === "admin" && <ScanControl />}
      </div>

      <div className="space-y-3">
        {isLoading && <p className="text-muted">Loading alerts…</p>}
        {alerts?.length === 0 && (
          <EmptyState
            title={filter === "open" ? "No open alerts" : "No alerts here"}
            body="Monitoring checks certificate validity, clarification deadlines and review times every hour."
          />
        )}
        {alerts?.map((a) => <AlertCard key={a.id} alert={a} />)}
      </div>
    </Layout>
  );
}

/** Admin: run monitoring now, optionally as of a future date (dev only, for demos). */
function ScanControl() {
  const queryClient = useQueryClient();
  const [asOf, setAsOf] = useState("");
  const scan = useMutation({
    mutationFn: () => runMonitoringScan(asOf ? new Date(`${asOf}T12:00:00`).toISOString() : undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
      queryClient.invalidateQueries({ queryKey: ["alert-summary"] });
    },
  });
  const r = scan.data;

  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <label className="flex items-center gap-2 text-muted">
        Check as of
        <input
          type="date"
          value={asOf}
          onChange={(e) => setAsOf(e.target.value)}
          className={`${inputClass.replace("mt-1.5 ", "")} h-9 w-auto`}
        />
      </label>
      <Button size="sm" onClick={() => scan.mutate()} disabled={scan.isPending}>
        Run monitoring now
      </Button>
      {asOf && <span className="text-review">Simulated date, dev only</span>}
      {r && (
        <span className="w-full text-right text-muted">
          {r.raised} raised, {r.overdue} overdue, {r.escalated} escalated, {r.resolved} resolved
        </span>
      )}
      {scan.error && <span className="w-full text-right text-fail">{scan.error.message}</span>}
    </div>
  );
}
