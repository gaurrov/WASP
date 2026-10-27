import { api, apiJson, tokenStore } from "./api";

export type ApplicationStatus =
  | "draft"
  | "submitted"
  | "processing"
  | "needs_review"
  | "clarification_requested"
  | "ready_for_decision"
  | "approved"
  | "rejected";

export interface ChecklistItem {
  doc_type: string;
  label: string;
  required: boolean;
  multiple: boolean;
}

export interface ApplicationType {
  code: string;
  label: string;
  checklist: ChecklistItem[];
}

export interface DeclaredValues {
  programme: string;
  sanctioned_intake: number;
  faculty_count: number;
}

export interface DocumentInfo {
  id: string;
  doc_type: string;
  filename: string;
  mime_type: string;
  sha256: string;
  page_count: number | null;
  version: number;
  supersedes_id: string | null;
  processing_status: ProcessingStatus;
  processing_error: string | null;
  detected_doc_type: string | null;
  detection_confidence: number | null;
  ocr_used: boolean | null;
  created_at: string;
  fact_count: number;
  low_confidence_count: number;
}

export type ProcessingStatus = "pending" | "processing" | "done" | "failed";

export interface Fact {
  id: string;
  field_name: string;
  value: unknown;
  raw_text: string | null;
  confidence: number;
  low_confidence: boolean;
  page: number | null;
  bbox: [number, number, number, number] | null;
  extractor: string;
}

export interface DocumentDetail {
  id: string;
  application_id: string;
  doc_type: string;
  filename: string;
  mime_type: string;
  version: number;
  processing_status: ProcessingStatus;
  processing_error: string | null;
  processed_at: string | null;
  detected_doc_type: string | null;
  detection_confidence: number | null;
  type_mismatch: boolean;
  ocr_used: boolean | null;
  pages: { number: number; width: number; height: number; ocr: boolean }[];
  facts: Fact[];
}

export interface ApplicationSummary {
  id: string;
  institution_id: string;
  institution_name: string;
  application_type: string;
  application_type_label: string;
  academic_year: string;
  status: ApplicationStatus;
  submitted_at: string | null;
  created_at: string;
  document_count: number;
}

export interface ApplicationDetail extends ApplicationSummary {
  declared: DeclaredValues;
  documents: DocumentInfo[];
  checklist: (ChecklistItem & { document_count: number; satisfied: boolean })[];
  missing_required: string[];
}

export const EDITABLE: ApplicationStatus[] = ["draft", "clarification_requested"];

export const fetchApplicationTypes = () => api<ApplicationType[]>("/application-types");
export const fetchApplications = () => api<ApplicationSummary[]>("/applications");
export const fetchApplication = (id: string) => api<ApplicationDetail>(`/applications/${id}`);

export const createApplication = (body: {
  application_type: string;
  academic_year: string;
  declared: DeclaredValues;
}) => apiJson<ApplicationDetail>("/applications", "POST", body);

export const submitApplication = (id: string) =>
  api<ApplicationDetail>(`/applications/${id}/submit`, { method: "POST" });

export function uploadDocument(
  applicationId: string,
  file: File,
  opts: { docType?: string; replacesId?: string },
) {
  const form = new FormData();
  form.append("file", file);
  if (opts.docType) form.append("doc_type", opts.docType);
  if (opts.replacesId) form.append("replaces_id", opts.replacesId);
  return api<DocumentInfo>(`/applications/${applicationId}/documents`, {
    method: "POST",
    body: form,
  });
}

export const deleteDocument = (applicationId: string, documentId: string) =>
  api<void>(`/applications/${applicationId}/documents/${documentId}`, { method: "DELETE" });

export const fetchDocument = (id: string) => api<DocumentDetail>(`/documents/${id}`);

export const reprocessDocument = (id: string) =>
  api<{ status: string }>(`/documents/${id}/reprocess`, { method: "POST" });

export const isProcessing = (status: ProcessingStatus) =>
  status === "pending" || status === "processing";

/** Fetches a rendered page with the bearer token and returns an object URL for <img>. */
export async function fetchPageImage(documentId: string, page: number): Promise<string> {
  const res = await fetch(`/api/documents/${documentId}/pages/${page}.png`, {
    headers: { Authorization: `Bearer ${tokenStore.get()}` },
  });
  if (!res.ok) throw new Error(`Could not render page ${page}`);
  return URL.createObjectURL(await res.blob());
}

export const humanize = (s: string) => s.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());

/** Opens a document in a new tab. Fetches with the bearer token, since a plain link can't. */
export async function openDocument(documentId: string): Promise<void> {
  const tab = window.open("", "_blank"); // open synchronously so popup blockers allow it
  const res = await fetch(`/api/documents/${documentId}/content`, {
    headers: { Authorization: `Bearer ${tokenStore.get()}` },
  });
  if (!res.ok || !tab) {
    tab?.close();
    throw new Error("Could not open document");
  }
  tab.location.href = URL.createObjectURL(await res.blob());
}

// --- Findings ---------------------------------------------------------------------------

export type FindingStatus =
  | "pass"
  | "fail"
  | "needs_review"
  | "not_applicable"
  | "unable_to_determine";
export type Severity = "info" | "low" | "medium" | "high" | "critical";

export interface Citation {
  chunk_id: string;
  source_title: string;
  source_version: string;
  section: string | null;
  heading: string | null;
  page: number | null;
  text: string;
  verified: boolean;
}

export interface Evidence {
  fact_id: string;
  document_id: string;
  filename: string;
  field_name: string;
  value: unknown;
  raw_text: string | null;
  confidence: number;
  low_confidence: boolean;
  page: number | null;
}

export interface Finding {
  id: string;
  status: FindingStatus;
  severity: Severity;
  reason: string;
  details: Record<string, unknown>;
  provisional: boolean;
  created_at: string;
  rule: {
    id: string;
    code: string;
    version: number;
    title: string;
    internal: boolean;
    status: RuleStatus;
    norm_note: string | null;
    source_section: string | null;
    source_page: number | null;
  };
  evidence: Evidence[];
  citations: Citation[];
  review: { outcome: "confirm" | "override"; comment: string | null; reviewer: string; created_at: string } | null;
}

export const fetchFindings = (applicationId: string) =>
  api<Finding[]>(`/applications/${applicationId}/findings`);

export const reevaluate = (applicationId: string) =>
  api<{ status: string }>(`/applications/${applicationId}/evaluate`, { method: "POST" });

// --- Rules and regulatory sources -------------------------------------------------------

export type RuleStatus = "draft" | "reviewed" | "approved" | "retired";

export interface Rule {
  id: string;
  rule_code: string;
  version: number;
  title: string;
  evaluator: string;
  severity: Severity;
  internal: boolean;
  status: RuleStatus;
  params: Record<string, unknown>;
  citation_query: string | null;
  norm_note: string | null;
  source_id: string | null;
  source_section: string | null;
  source_page: number | null;
}

export interface RegulatorySource {
  id: string;
  title: string;
  source_type: string;
  version: string;
  effective_from: string | null;
  effective_to: string | null;
  source_url: string | null;
  ingest_status: ProcessingStatus;
  ingest_error: string | null;
  chunk_count: number;
  created_at: string;
}

export interface SearchHit {
  chunk_id: string;
  source_id: string;
  source_title: string;
  source_version: string;
  section: string | null;
  heading: string | null;
  page: number | null;
  text: string;
  score: number;
  matched_by: string[];
}

export const fetchRules = () => api<Rule[]>("/rules");
export const fetchRuleCandidates = (ruleId: string) =>
  api<SearchHit[]>(`/rules/${ruleId}/candidates`);
export const verifyRule = (ruleId: string, chunkId: string) =>
  apiJson<Rule>(`/rules/${ruleId}/verify`, "POST", { chunk_id: chunkId });

export const fetchSources = () => api<RegulatorySource[]>("/regulatory/sources");
export const searchRegulations = (q: string) =>
  api<SearchHit[]>(`/regulatory/search?${new URLSearchParams({ q, k: "8" })}`);

export function uploadSource(file: File, fields: Record<string, string>) {
  const form = new FormData();
  form.append("file", file);
  for (const [k, v] of Object.entries(fields)) if (v) form.append(k, v);
  return api<RegulatorySource>("/regulatory/sources", { method: "POST", body: form });
}

// --- Workflow ---------------------------------------------------------------------------

export interface WorkflowEvent {
  event_type: string;
  from_status: string | null;
  to_status: string | null;
  actor: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface Workflow {
  started: boolean;
  finished: boolean;
  waiting_for: "extraction" | "reviewer" | "institution" | null;
  round: number;
  rechecked: string[];
  total_rules: number;
  clarification: { message: string; finding_ids: string[]; requested_at: string } | null;
  decision: { decision: "approve" | "reject"; reason: string; decided_at: string } | null;
  unreviewed_findings: number;
  confirmed_deficiencies: number;
  events: WorkflowEvent[];
}

export const fetchWorkflow = (applicationId: string) =>
  api<Workflow>(`/applications/${applicationId}/workflow`);

export const reviewFinding = (findingId: string, outcome: "confirm" | "override", comment?: string) =>
  apiJson<{ status: string }>(`/findings/${findingId}/review`, "POST", { outcome, comment });

export const requestClarification = (applicationId: string, message: string, findingIds: string[]) =>
  apiJson<{ status: string }>(`/applications/${applicationId}/clarification`, "POST", {
    message,
    finding_ids: findingIds,
  });

export const decideApplication = (applicationId: string, decision: "approve" | "reject", reason: string) =>
  apiJson<{ status: string }>(`/applications/${applicationId}/decision`, "POST", { decision, reason });
