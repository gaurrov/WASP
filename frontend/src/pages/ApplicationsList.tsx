import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { fetchApplications } from "../applications";
import { useAuth } from "../auth";
import Layout from "../components/Layout";
import StatusBadge from "../components/StatusBadge";

const fmtDate = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString() : "—");

export default function ApplicationsList() {
  const { user } = useAuth();
  const { data: apps, isLoading, error } = useQuery({
    queryKey: ["applications"],
    queryFn: fetchApplications,
  });
  const isInstitution = user?.role === "institution";

  return (
    <Layout>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-900">
          {isInstitution ? "My applications" : "Review queue"}
        </h1>
        {isInstitution && (
          <Link
            to="/applications/new"
            className="rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white"
          >
            New application
          </Link>
        )}
      </div>

      {error && <p className="mt-6 text-sm text-red-600">{error.message}</p>}
      {isLoading && <p className="mt-6 text-sm text-slate-500">Loading…</p>}
      {apps?.length === 0 && (
        <p className="mt-6 rounded-lg border border-dashed bg-white p-8 text-center text-sm text-slate-500">
          {isInstitution
            ? "No applications yet. Create one to start uploading documents."
            : "No submitted applications to review."}
        </p>
      )}

      {apps && apps.length > 0 && (
        <div className="mt-6 overflow-x-auto rounded-lg border bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                {!isInstitution && <th className="px-4 py-3 font-medium">Institution</th>}
                <th className="px-4 py-3 font-medium">Type</th>
                <th className="px-4 py-3 font-medium">Academic year</th>
                <th className="px-4 py-3 font-medium">Documents</th>
                <th className="px-4 py-3 font-medium">Submitted</th>
                <th className="px-4 py-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {apps.map((a) => (
                <tr key={a.id} className="hover:bg-slate-50">
                  {!isInstitution && (
                    <td className="px-4 py-3 font-medium text-slate-900">
                      <Link to={`/applications/${a.id}`}>{a.institution_name}</Link>
                    </td>
                  )}
                  <td className="px-4 py-3">
                    <Link to={`/applications/${a.id}`} className="text-slate-900 hover:underline">
                      {a.application_type_label}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-slate-600">{a.academic_year}</td>
                  <td className="px-4 py-3 text-slate-600">{a.document_count}</td>
                  <td className="px-4 py-3 text-slate-600">{fmtDate(a.submitted_at)}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={a.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Layout>
  );
}
