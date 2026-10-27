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
  processing_status: string;
  created_at: string;
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
