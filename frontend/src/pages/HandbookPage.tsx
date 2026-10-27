import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { fetchSources, searchRegulations, uploadSource } from "../applications";
import { useAuth } from "../auth";
import Layout from "../components/Layout";

const inputClass = "mt-1 w-full rounded-md border px-3 py-2 text-sm";

export default function HandbookPage() {
  const { user } = useAuth();
  const { data: sources } = useQuery({
    queryKey: ["sources"],
    queryFn: fetchSources,
    refetchInterval: (q) =>
      q.state.data?.some((s) => s.ingest_status === "pending" || s.ingest_status === "processing")
        ? 2000
        : false,
  });

  return (
    <Layout>
      <h1 className="text-xl font-semibold text-slate-900">Regulatory handbook</h1>
      <p className="mt-1 max-w-3xl text-sm text-slate-500">
        Official sources are split into clauses and indexed for hybrid (keyword + semantic) search.
        Findings cite these clauses; each source applies only within its effective dates.
      </p>

      <section className="mt-6 rounded-lg border bg-white">
        <h2 className="border-b px-4 py-3 text-sm font-medium text-slate-900">Sources</h2>
        {sources?.length ? (
          <ul className="divide-y">
            {sources.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
                <div>
                  <span className="font-medium text-slate-900">{s.title}</span>{" "}
                  <span className="text-slate-500">{s.version}</span>
                  <div className="text-xs text-slate-500">
                    In force {s.effective_from ?? "—"} to {s.effective_to ?? "—"}
                    {s.source_url && (
                      <>
                        {" · "}
                        <a href={s.source_url} target="_blank" rel="noreferrer" className="underline">
                          official link
                        </a>
                      </>
                    )}
                  </div>
                </div>
                <span className="text-xs text-slate-600">
                  {s.ingest_status === "done"
                    ? `${s.chunk_count} clauses indexed`
                    : s.ingest_status === "failed"
                      ? `failed: ${s.ingest_error}`
                      : "indexing…"}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="px-4 py-6 text-sm text-slate-500">
            No sources yet. Upload the AICTE Approval Process Handbook (APH) 2024-27 PDF to enable
            citations and rule verification.
          </p>
        )}
        {user?.role === "admin" && <UploadForm />}
      </section>

      <SearchBox />
    </Layout>
  );
}

function UploadForm() {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [fields, setFields] = useState({
    title: "AICTE Approval Process Handbook",
    version: "2024-27",
    effective_from: "2024-07-01",
    effective_to: "2027-06-30",
    source_url: "",
  });
  const upload = useMutation({
    mutationFn: () => uploadSource(file!, fields),
    onSuccess: () => {
      setFile(null);
      queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
  });
  const set = (k: keyof typeof fields) => (e: { target: { value: string } }) =>
    setFields({ ...fields, [k]: e.target.value });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (file) upload.mutate();
  };

  return (
    <form onSubmit={onSubmit} className="grid gap-3 border-t bg-slate-50 px-4 py-4 sm:grid-cols-2">
      <label className="block sm:col-span-2">
        <span className="text-xs font-medium text-slate-700">PDF</span>
        <input
          type="file"
          accept="application/pdf"
          required
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="mt-1 block w-full text-sm"
        />
      </label>
      <label className="block">
        <span className="text-xs font-medium text-slate-700">Title</span>
        <input required value={fields.title} onChange={set("title")} className={inputClass} />
      </label>
      <label className="block">
        <span className="text-xs font-medium text-slate-700">Version</span>
        <input required value={fields.version} onChange={set("version")} className={inputClass} />
      </label>
      <label className="block">
        <span className="text-xs font-medium text-slate-700">Effective from</span>
        <input type="date" value={fields.effective_from} onChange={set("effective_from")} className={inputClass} />
      </label>
      <label className="block">
        <span className="text-xs font-medium text-slate-700">Effective to</span>
        <input type="date" value={fields.effective_to} onChange={set("effective_to")} className={inputClass} />
      </label>
      <label className="block sm:col-span-2">
        <span className="text-xs font-medium text-slate-700">Official URL</span>
        <input value={fields.source_url} onChange={set("source_url")} className={inputClass} />
      </label>
      {upload.error && <p className="text-sm text-red-600 sm:col-span-2">{upload.error.message}</p>}
      <div className="sm:col-span-2">
        <button
          type="submit"
          disabled={!file || upload.isPending}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {upload.isPending ? "Uploading…" : "Upload and index"}
        </button>
      </div>
    </form>
  );
}

function SearchBox() {
  const [q, setQ] = useState("");
  const search = useMutation({ mutationFn: searchRegulations });

  return (
    <section className="mt-6 rounded-lg border bg-white p-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (q.trim()) search.mutate(q);
        }}
        className="flex gap-2"
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Ask the handbook, e.g. “student faculty ratio for UG engineering”"
          className="flex-1 rounded-md border px-3 py-2 text-sm"
        />
        <button className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white">
          Search
        </button>
      </form>
      {search.data && search.data.length === 0 && (
        <p className="mt-4 text-sm text-slate-500">No matching clauses.</p>
      )}
      <div className="mt-4 space-y-3">
        {search.data?.map((h) => (
          <div key={h.chunk_id} className="rounded-md border p-3">
            <div className="text-xs font-medium text-slate-900">
              {h.source_title} {h.source_version}
              {h.section && ` · § ${h.section}`}
              {h.heading && ` ${h.heading}`}
              {h.page && ` · p. ${h.page}`}
              <span className="ml-2 font-normal text-slate-400">{h.matched_by.join(" + ")}</span>
            </div>
            <p className="mt-1 line-clamp-6 whitespace-pre-line text-sm text-slate-700">{h.text}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
