import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Circle, CircleCheck, CircleDashed, FileText } from "lucide-react";
import { useState, type ChangeEvent, type ReactNode } from "react";
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
import Layout from "../components/Layout";
import {
  Button,
  ErrorText,
  FileButton,
  PageHeader,
  Panel,
  Pill,
  Stamp,
  StatusPill,
  caseRef,
  formatDate,
} from "../components/ui";
import { CaseNotice, NextStep, Timeline } from "../components/WorkflowPanel";

export default function ApplicationDetail() {
  const { id = "" } = useParams();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const { data: app, isLoading, error: loadError } = useQuery({
    queryKey: ["application", id],
    queryFn: () => fetchApplication(id),
    // Poll while documents are being read or checks are running.
    refetchInterval: (q) => {
      const a = q.state.data;
      const working =
        a?.status === "submitted" ||
        a?.status === "processing" ||
        a?.documents.some((d) => isProcessing(d.processing_status));
      return working ? 2000 : false;
    },
  });

  const { data: workflow } = useQuery({
    queryKey: ["workflow", id],
    queryFn: () => fetchWorkflow(id),
    enabled: !!app && app.status !== "draft",
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

  if (isLoading) return <Layout>Loading application…</Layout>;
  if (loadError || !app) {
    return (
      <Layout>
        <ErrorText>{loadError?.message ?? "This application doesn't exist or isn't visible to you."}</ErrorText>
      </Layout>
    );
  }

  const isInstitution = user?.role === "institution";
  const canEdit = isInstitution && EDITABLE.includes(app.status);
  // Expiring certificates can be replaced even after submission or approval.
  const renewalDocIds = new Set(
    isInstitution
      ? (appAlerts ?? [])
          .filter((a) => a.alert_type === "certificate_expiry")
          .map((a) => String(a.details.document_id))
      : [],
  );

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
      ? `${missing} required document type(s) are still missing. They'll be recorded as deficiencies. Submit anyway?`
      : "Submit this application for review? Documents can't be changed afterwards unless AICTE asks for a clarification.";
    if (window.confirm(msg)) submit.mutate();
  };

  return (
    <Layout>
      <PageHeader
        back={{ to: "/applications", label: isInstitution ? "Applications" : "Review queue" }}
        title={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-2">
            {isInstitution ? `${app.application_type_label} ${app.academic_year}` : app.institution_name}
            <StatusPill status={app.status} />
          </span>
        }
        description={
          <>
            {isInstitution ? app.institution_name : `${app.application_type_label} ${app.academic_year}`}
            <span className="mx-2 text-rule-strong" aria-hidden>
              |
            </span>
            <span className="whitespace-nowrap">{caseRef(app)}</span>
            {app.submitted_at && (
              <>
                <span className="mx-2 text-rule-strong" aria-hidden>
                  |
                </span>
                Submitted {formatDate(app.submitted_at)}
              </>
            )}
          </>
        }
        actions={workflow?.decision && <Stamp decision={workflow.decision.decision} date={workflow.decision.decided_at} />}
      />

      {error && (
        <div className="mb-6">
          <ErrorText>{error}</ErrorText>
        </div>
      )}

      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_19rem]">
        <div className="min-w-0 space-y-8">
          <CaseNotice app={app} workflow={workflow} />

          {appAlerts && appAlerts.length > 0 && (
            <Panel title="Open alerts">
              <div className="divide-y">
                {appAlerts.map((a) => (
                  <AlertCard key={a.id} alert={a} variant="row" />
                ))}
              </div>
            </Panel>
          )}

          {app.status !== "draft" && <FindingsPanel app={app} workflow={workflow} />}

          <Panel
            title="Documents"
            actions={
              <span className="text-sm text-muted">
                {app.documents.length} file{app.documents.length === 1 ? "" : "s"}
              </span>
            }
          >
            <ul className="divide-y">
              {app.checklist.map((item) => (
                <ChecklistGroup
                  key={item.doc_type}
                  item={item}
                  docs={app.documents.filter((d) => d.doc_type === item.doc_type)}
                  upload={
                    canEdit && (item.multiple || item.document_count === 0) ? (
                      <FileButton onFiles={onUpload(item.doc_type)} multiple={item.multiple} disabled={busy}>
                        Upload
                      </FileButton>
                    ) : null
                  }
                  renderDoc={(doc) => (
                    <DocumentRow
                      key={doc.id}
                      doc={doc}
                      canReplace={canEdit || renewalDocIds.has(doc.id)}
                      isRenewal={renewalDocIds.has(doc.id) && !canEdit}
                      canDelete={canEdit && app.status === "draft"}
                      busy={busy}
                      onReplace={onReplace(doc)}
                      onDelete={() => run(() => deleteDocument(app.id, doc.id))}
                    />
                  )}
                  isNotable={(doc) => renewalDocIds.has(doc.id)}
                />
              ))}
            </ul>
          </Panel>

          {workflow?.started && <Timeline workflow={workflow} />}
        </div>

        <aside className="space-y-6 lg:sticky lg:top-8">
          {canEdit && <SubmitPanel app={app} onSubmit={onSubmit} disabled={submit.isPending || busy} />}
          <NextStep app={app} workflow={workflow} />
          <Panel title="Declared by the institution">
            <dl className="divide-y text-[15px]">
              {[
                ["Programme", app.declared.programme],
                ["Sanctioned intake", `${app.declared.sanctioned_intake} per year`],
                ["Faculty", app.declared.faculty_count],
              ].map(([label, value]) => (
                <div key={label} className="px-5 py-3">
                  <dt className="text-sm text-muted">{label}</dt>
                  <dd className="font-bold">{value}</dd>
                </div>
              ))}
            </dl>
          </Panel>
        </aside>
      </div>
    </Layout>
  );
}

const COLLAPSE_OVER = 3;

/** One checklist item and its files. Long groups collapse, but files that need attention
 * (to verify, unreadable, still being read, renewal due) always stay visible. */
function ChecklistGroup({
  item,
  docs,
  upload,
  renderDoc,
  isNotable,
}: {
  item: Detail["checklist"][number];
  docs: DocumentInfo[];
  upload: ReactNode;
  renderDoc: (doc: DocumentInfo) => ReactNode;
  isNotable: (doc: DocumentInfo) => boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const notable = (d: DocumentInfo) =>
    d.low_confidence_count > 0 || d.processing_status !== "done" || isNotable(d);
  const collapsible = docs.length > COLLAPSE_OVER;
  const shown = collapsible && !expanded ? docs.filter(notable) : docs;
  const hidden = docs.length - shown.length;

  return (
    <li className="px-5 py-3.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <ChecklistMark uploaded={item.document_count > 0} required={item.required} />
          <span className="font-bold">{item.label}</span>
          {collapsible && <span className="text-sm text-muted">{docs.length} files</span>}
          {!item.required && <span className="text-sm text-muted">optional</span>}
          {item.required && item.document_count === 0 && <Pill tone="review">Missing</Pill>}
        </div>
        {upload}
      </div>
      {(shown.length > 0 || hidden > 0) && (
        <ul className="mt-2 space-y-1 pl-[1.85rem]">
          {shown.map(renderDoc)}
          {collapsible && (
            <li>
              <button
                onClick={() => setExpanded(!expanded)}
                aria-expanded={expanded}
                className="py-1 text-sm font-bold text-stamp underline-offset-2 hover:underline"
              >
                {expanded ? "Show fewer" : `Show all ${docs.length} files${hidden < docs.length ? ` (${hidden} more)` : ""}`}
              </button>
            </li>
          )}
        </ul>
      )}
    </li>
  );
}

function SubmitPanel({ app, onSubmit, disabled }: { app: Detail; onSubmit: () => void; disabled: boolean }) {
  const required = app.checklist.filter((c) => c.required);
  const done = required.filter((c) => c.satisfied).length;
  const resubmit = app.status === "clarification_requested";
  return (
    <Panel title={resubmit ? "Resubmit" : "Submit for review"}>
      <div className="space-y-4 px-5 py-4">
        <div>
          <div className="flex justify-between text-sm">
            <span>Required documents</span>
            <span className="font-bold">
              {done} of {required.length}
            </span>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-paper" aria-hidden>
            <div className="h-full rounded-full bg-pass" style={{ width: `${(done / required.length) * 100}%` }} />
          </div>
          {app.missing_required.length > 0 && (
            <p className="mt-2 text-sm text-muted">
              Missing: {app.checklist.filter((c) => !c.satisfied).map((c) => c.label).join(", ")}.
            </p>
          )}
        </div>
        <Button variant="primary" className="w-full" onClick={onSubmit} disabled={disabled}>
          {resubmit ? "Resubmit" : "Submit for review"}
        </Button>
      </div>
    </Panel>
  );
}

function DocumentRow({
  doc,
  canReplace,
  isRenewal,
  canDelete,
  busy,
  onReplace,
  onDelete,
}: {
  doc: DocumentInfo;
  canReplace: boolean;
  isRenewal: boolean;
  canDelete: boolean;
  busy: boolean;
  onReplace: (e: ChangeEvent<HTMLInputElement>) => void;
  onDelete: () => void;
}) {
  const mismatch =
    doc.detected_doc_type &&
    doc.detected_doc_type !== doc.doc_type &&
    doc.detected_doc_type !== "unclassified" &&
    (doc.detection_confidence ?? 0) >= 0.6;

  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 py-1 text-sm">
      <FileText size={15} className="text-faint" aria-hidden />
      <Link to={`/documents/${doc.id}`} className="font-bold text-stamp underline-offset-2 hover:underline">
        {doc.filename}
      </Link>
      <span className="text-muted">
        {doc.page_count != null && `${doc.page_count} page${doc.page_count === 1 ? "" : "s"}, `}v{doc.version}
      </span>
      {isProcessing(doc.processing_status) ? (
        <span className="text-muted">reading…</span>
      ) : doc.processing_status === "failed" ? (
        <Pill tone="fail">Couldn't be read</Pill>
      ) : (
        <>
          <span className="text-muted">{doc.fact_count} fields</span>
          {doc.low_confidence_count > 0 && <Pill tone="review">{doc.low_confidence_count} to verify</Pill>}
          {mismatch && <Pill tone="review">Looks like a different document</Pill>}
        </>
      )}
      <span className="ml-auto flex gap-1">
        {canReplace && (
          <FileButton onFiles={onReplace} disabled={busy} variant={isRenewal ? "primary" : "ghost"}>
            {isRenewal ? "Upload renewal" : "Replace"}
          </FileButton>
        )}
        {canDelete && (
          <Button size="sm" variant="ghost" onClick={onDelete} disabled={busy}>
            Delete
          </Button>
        )}
      </span>
    </li>
  );
}

function ChecklistMark({ uploaded, required }: { uploaded: boolean; required: boolean }) {
  if (uploaded) return <CircleCheck size={19} className="text-pass" aria-label="Uploaded" />;
  if (required) return <Circle size={19} className="text-review" aria-label="Required, missing" />;
  return <CircleDashed size={19} className="text-faint" aria-label="Optional" />;
}
