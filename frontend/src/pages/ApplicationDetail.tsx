import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ChangeEvent } from "react";
import { Link, useParams } from "react-router";
import {
  EDITABLE,
  deleteDocument,
  fetchAlerts,
  fetchApplication,
  fetchWorkflow,
  isProcessing,
  submitApplication,
  uploadDocument,
  type ApplicationDetail as Detail,
  type DocumentInfo,
} from "../applications";
import { useAuth } from "../auth";
import AlertCard from "../components/AlertCard";
import FindingsPanel from "../components/FindingsPanel";
import { CaseBanner, Timeline } from "../components/WorkflowPanel";
import Layout from "../components/Layout";
import StatusBadge from "../components/StatusBadge";

const ACCEPT = ".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg";

export default function ApplicationDetail() {
  const { id = "" } = useParams();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const { data: app, isLoading, error: loadError } = useQuery({
    queryKey: ["application", id],
    queryFn: () => fetchApplication(id),
    // Poll while any document is still being extracted.
    refetchInterval: (q) => {
      const app = q.state.data;
      const busy =
        app?.status === "submitted" ||
        app?.status === "processing" ||
        app?.documents.some((d) => isProcessing(d.processing_status));
      return busy ? 2000 : false;
    },
  });

  const { data: workflow } = useQuery({
    queryKey: ["workflow", id],
    queryFn: () => fetchWorkflow(id),
    enabled: !!app && app.status !== "draft",
    // Poll while the case is running in the background (extraction / evaluation).
    refetchInterval: (q) =>
      !q.state.data?.started ||
      q.state.data.waiting_for === "extraction" ||
      app?.status === "submitted" ||
      app?.status === "processing"
        ? 2000
        : false,
  });

  const { data: appAlerts } = useQuery({
    queryKey: ["alerts", "application", id],
    queryFn: () => fetchAlerts({ status: "open", application_id: id }),
    enabled: !!app && app.status !== "draft",
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["alerts"] });
    for (const key of ["application", "workflow", "findings"]) {
      queryClient.invalidateQueries({ queryKey: [key, id] });
    }
    queryClient.invalidateQueries({ queryKey: ["applications"] });
  };

  const run = async (action: () => Promise<unknown>) => {
    setError(null);
    setBusy(true);
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      refresh();
    }
  };

  const submit = useMutation({
    mutationFn: () => submitApplication(id),
    onSuccess: refresh,
    onError: (e) => setError(e.message),
  });

  if (isLoading) return <Layout>Loading…</Layout>;
  if (loadError || !app) {
    return (
      <Layout>
        <p className="text-sm text-red-600">{loadError?.message ?? "Not found"}</p>
      </Layout>
    );
  }

  const canEdit = user?.role === "institution" && EDITABLE.includes(app.status);
  // Expiring certificates can be replaced even after submission/approval (compliance update).
  const renewalDocIds = new Set(
    user?.role === "institution"
      ? (appAlerts ?? [])
          .filter((a) => a.alert_type === "certificate_expiry")
          .map((a) => String(a.details.document_id))
      : [],
  );
  const isDraft = app.status === "draft";

  const onUpload = (docType: string) => (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    run(async () => {
      for (const file of files) await uploadDocument(app.id, file, { docType });
    });
  };

  const onReplace = (doc: DocumentInfo) => (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) run(() => uploadDocument(app.id, file, { replacesId: doc.id }));
  };

  const onSubmit = () => {
    const missing = app.missing_required.length;
    const msg = missing
      ? `${missing} required document type(s) are still missing. They will be flagged as deficiencies during review. Submit anyway?`
      : "Submit this application for review? Documents can't be changed afterwards unless clarification is requested.";
    if (window.confirm(msg)) submit.mutate();
  };

  return (
    <Layout>
      <Link to="/applications" className="text-sm text-slate-500 hover:text-slate-900">
        ← {user?.role === "institution" ? "My applications" : "Review queue"}
      </Link>

      <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold text-slate-900">
              {app.application_type_label} · {app.academic_year}
            </h1>
            <StatusBadge status={app.status} />
          </div>
          <p className="mt-1 text-sm text-slate-500">
            {app.institution_name}
            {app.submitted_at && ` · submitted ${new Date(app.submitted_at).toLocaleString()}`}
          </p>
        </div>
        {canEdit && (
          <button
            onClick={onSubmit}
            disabled={submit.isPending || busy}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {app.status === "clarification_requested" ? "Resubmit" : "Submit for review"}
          </button>
        )}
      </div>

      {error && (
        <p className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}
      {app.status === "draft" && (
        <MissingBanner app={app} isInstitution={user?.role === "institution"} />
      )}
      <CaseBanner app={app} workflow={workflow} />
      {appAlerts && appAlerts.length > 0 && (
        <div className="mt-4 space-y-2">
          {appAlerts.map((a) => (
            <AlertCard key={a.id} alert={a} compact />
          ))}
        </div>
      )}
      {app.status !== "draft" && <FindingsPanel app={app} workflow={workflow} />}

      <div className="mt-6 grid gap-6 lg:grid-cols-[16rem_1fr]">
        <section className="h-fit rounded-lg border bg-white p-4">
          <h2 className="text-sm font-medium text-slate-900">Declared values</h2>
          <dl className="mt-3 space-y-3 text-sm">
            <div>
              <dt className="text-xs text-slate-500">Programme</dt>
              <dd className="text-slate-900">{app.declared.programme}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Sanctioned intake</dt>
              <dd className="text-slate-900">{app.declared.sanctioned_intake}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Faculty count</dt>
              <dd className="text-slate-900">{app.declared.faculty_count}</dd>
            </div>
          </dl>
        </section>

        <section className="rounded-lg border bg-white">
          <h2 className="border-b px-4 py-3 text-sm font-medium text-slate-900">
            Document checklist
          </h2>
          <ul className="divide-y">
            {app.checklist.map((item) => {
              const docs = app.documents.filter((d) => d.doc_type === item.doc_type);
              return (
                <li key={item.doc_type} className="px-4 py-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <ChecklistIcon uploaded={item.document_count > 0} required={item.required} />
                      <span className="text-sm text-slate-900">{item.label}</span>
                      {!item.required && <span className="text-xs text-slate-400">optional</span>}
                    </div>
                    {canEdit && (item.multiple || docs.length === 0) && (
                      <label
                        className={`cursor-pointer rounded-md border px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-50 ${busy ? "opacity-50" : ""}`}
                      >
                        Upload
                        <input
                          type="file"
                          accept={ACCEPT}
                          multiple={item.multiple}
                          disabled={busy}
                          onChange={onUpload(item.doc_type)}
                          className="hidden"
                        />
                      </label>
                    )}
                  </div>
                  {docs.length > 0 && (
                    <ul className="mt-2 space-y-1 pl-7">
                      {docs.map((doc) => (
                        <li key={doc.id} className="flex flex-wrap items-center gap-x-3 text-xs">
                          <Link to={`/documents/${doc.id}`} className="text-blue-700 hover:underline">
                            {doc.filename}
                          </Link>
                          <span className="text-slate-400">
                            {doc.page_count != null && `${doc.page_count} p · `}v{doc.version}
                          </span>
                          <ProcessingChip doc={doc} />
                          {(canEdit || renewalDocIds.has(doc.id)) && (
                            <label
                              className={
                                renewalDocIds.has(doc.id) && !canEdit
                                  ? "cursor-pointer rounded bg-slate-900 px-1.5 text-white"
                                  : "cursor-pointer text-slate-500 hover:text-slate-900"
                              }
                            >
                              {renewalDocIds.has(doc.id) && !canEdit ? "Upload renewal" : "Replace"}
                              <input
                                type="file"
                                accept={ACCEPT}
                                disabled={busy}
                                onChange={onReplace(doc)}
                                className="hidden"
                              />
                            </label>
                          )}
                          {canEdit && isDraft && (
                            <button
                              onClick={() => run(() => deleteDocument(app.id, doc.id))}
                              className="text-slate-500 hover:text-red-600"
                            >
                              Delete
                            </button>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      </div>
      {workflow?.started && <Timeline workflow={workflow} />}
    </Layout>
  );
}

function ProcessingChip({ doc }: { doc: DocumentInfo }) {
  if (isProcessing(doc.processing_status)) {
    return <span className="text-slate-400">extracting…</span>;
  }
  if (doc.processing_status === "failed") {
    return <span className="text-red-600">extraction failed</span>;
  }
  const mismatch =
    doc.detected_doc_type &&
    doc.detected_doc_type !== doc.doc_type &&
    doc.detected_doc_type !== "unclassified" &&
    (doc.detection_confidence ?? 0) >= 0.6;
  return (
    <>
      <span className="text-slate-500">{doc.fact_count} fields</span>
      {doc.low_confidence_count > 0 && (
        <span className="rounded bg-amber-100 px-1.5 text-amber-900">
          {doc.low_confidence_count} to verify
        </span>
      )}
      {mismatch && (
        <span className="rounded bg-amber-100 px-1.5 text-amber-900">type mismatch?</span>
      )}
    </>
  );
}

function MissingBanner({ app, isInstitution }: { app: Detail; isInstitution: boolean }) {
  if (app.missing_required.length === 0) return null;
  const labels = app.checklist.filter((c) => !c.satisfied).map((c) => c.label);
  return (
    <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
      <span className="font-medium">
        {isInstitution ? "Required documents missing: " : "Incomplete submission — missing: "}
      </span>
      {labels.join(", ")}
    </div>
  );
}

function ChecklistIcon({ uploaded, required }: { uploaded: boolean; required: boolean }) {
  if (uploaded) {
    return (
      <span className="flex size-5 items-center justify-center rounded-full bg-emerald-100 text-xs text-emerald-700">
        ✓
      </span>
    );
  }
  if (required) {
    return (
      <span className="flex size-5 items-center justify-center rounded-full bg-amber-100 text-xs text-amber-800">
        !
      </span>
    );
  }
  return <span className="size-5 rounded-full border border-dashed" />;
}
