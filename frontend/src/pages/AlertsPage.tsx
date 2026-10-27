import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fetchAlerts, runMonitoringScan } from "../applications";
import { useAuth } from "../auth";
import AlertCard from "../components/AlertCard";
import Layout from "../components/Layout";

type Filter = "open" | "resolved" | "all";

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
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Alerts</h1>
          <p className="mt-1 text-sm text-slate-500">
            Compliance obligations found by monitoring. Alerts close automatically when the data
            shows the obligation is met.
          </p>
        </div>
        <div className="flex rounded-md border bg-white p-0.5 text-sm">
          {(["open", "resolved", "all"] as Filter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`rounded px-3 py-1 capitalize ${filter === f ? "bg-slate-900 text-white" : "text-slate-600"}`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {user?.role === "admin" && <ScanControl />}

      <div className="mt-6 space-y-3">
        {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
        {alerts?.length === 0 && (
          <p className="rounded-lg border border-dashed bg-white p-8 text-center text-sm text-slate-500">
            No {filter === "all" ? "" : filter} alerts.
          </p>
        )}
        {alerts?.map((a) => <AlertCard key={a.id} alert={a} />)}
      </div>
    </Layout>
  );
}

/** Admin: run the monitoring scan now, optionally "as of" a future date (dev demo only). */
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
    <div className="mt-4 flex flex-wrap items-center gap-3 rounded-lg border bg-white px-4 py-3 text-sm">
      <span className="font-medium text-slate-900">Monitoring scan</span>
      <label className="flex items-center gap-2 text-slate-600">
        as of
        <input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} className="rounded border px-2 py-1" />
      </label>
      <button
        onClick={() => scan.mutate()}
        disabled={scan.isPending}
        className="rounded-md bg-slate-900 px-3 py-1.5 text-white disabled:opacity-50"
      >
        Run scan
      </button>
      {asOf && <span className="text-xs text-amber-700">Simulated date (dev only)</span>}
      {r && (
        <span className="text-xs text-slate-500">
          raised {r.raised} · overdue {r.overdue} · escalated {r.escalated} · resolved {r.resolved} · reopened {r.reopened}
        </span>
      )}
      {scan.error && <span className="text-xs text-red-600">{scan.error.message}</span>}
    </div>
  );
}
