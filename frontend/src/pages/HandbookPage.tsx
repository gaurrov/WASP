import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useState, type FormEvent } from "react";
import { fetchSources, searchRegulations, uploadSource } from "../applications";
import { useAuth } from "../auth";
import Layout from "../components/Layout";
import { Button, EmptyState, ErrorText, Field, PageHeader, Panel, Pill, formatDate, inputClass } from "../components/ui";

export default function HandbookPage() {
  const { user } = useAuth();
  const { data: sources } = useQuery({
    queryKey: ["sources"],
    queryFn: fetchSources,
    refetchInterval: (q) =>
      q.state.data?.some((s) => s.ingest_status === "pending" || s.ingest_status === "processing") ? 2000 : false,
  });

  return (
    <Layout>
      <PageHeader
        title="Regulatory handbook"
        description="Official sources, split into clauses and searchable by wording or meaning. Findings cite these clauses, and each edition applies only within its effective dates."
      />

      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <SearchBox hasSources={!!sources?.length} />

        <div className="space-y-6">
          <Panel title="Sources">
            {sources?.length ? (
              <ul className="divide-y">
                {sources.map((s) => (
                  <li key={s.id} className="px-5 py-3.5">
                    <p className="font-bold">
                      {s.title} {s.version}
                    </p>
                    <p className="text-sm text-muted">
                      In force {formatDate(s.effective_from)} to {formatDate(s.effective_to)}
                    </p>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
                      {s.ingest_status === "done" ? (
                        <Pill tone="pass">{s.chunk_count} clauses indexed</Pill>
                      ) : s.ingest_status === "failed" ? (
                        <Pill tone="fail">Indexing failed</Pill>
                      ) : (
                        <Pill tone="info">Indexing…</Pill>
                      )}
                      {s.source_url && (
                        <a href={s.source_url} target="_blank" rel="noreferrer" className="text-stamp hover:underline">
                          Official copy
                        </a>
                      )}
                    </div>
                    {s.ingest_error && <p className="mt-1 text-sm text-fail">{s.ingest_error}</p>}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="px-5 py-4 text-sm text-muted">
                No handbook loaded yet. Until one is, findings can't cite clauses and AICTE norms stay
                provisional.
              </p>
            )}
          </Panel>
          {user?.role === "admin" && <UploadForm />}
        </div>
      </div>
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
    <Panel title="Add an edition">
      <form onSubmit={onSubmit} className="space-y-4 px-5 py-4">
        <Field label="PDF">
          <input
            type="file"
            accept="application/pdf"
            required
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="mt-1.5 block w-full text-sm file:mr-3 file:rounded-[var(--radius-control)] file:border file:border-rule-strong file:bg-sheet file:px-3 file:py-1.5 file:text-sm file:font-medium"
          />
        </Field>
        <Field label="Title">
          <input required value={fields.title} onChange={set("title")} className={inputClass} />
        </Field>
        <Field label="Edition">
          <input required value={fields.version} onChange={set("version")} className={inputClass} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="In force from">
            <input type="date" value={fields.effective_from} onChange={set("effective_from")} className={inputClass} />
          </Field>
          <Field label="Until">
            <input type="date" value={fields.effective_to} onChange={set("effective_to")} className={inputClass} />
          </Field>
        </div>
        <Field label="Official URL">
          <input value={fields.source_url} onChange={set("source_url")} className={inputClass} />
        </Field>
        {upload.error && <ErrorText>{upload.error.message}</ErrorText>}
        <Button type="submit" variant="primary" disabled={!file || upload.isPending} className="w-full">
          {upload.isPending ? "Uploading…" : "Upload and index"}
        </Button>
      </form>
    </Panel>
  );
}

function SearchBox({ hasSources }: { hasSources: boolean }) {
  const [q, setQ] = useState("");
  const search = useMutation({ mutationFn: searchRegulations });

  return (
    <div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (q.trim()) search.mutate(q);
        }}
        className="flex gap-2"
      >
        <label className="relative flex-1">
          <span className="sr-only">Search the handbook</span>
          <Search size={18} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-faint" aria-hidden />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search the handbook, e.g. student faculty ratio for UG engineering"
            className={`${inputClass.replace("mt-1.5", "")} h-11 pl-10`}
          />
        </label>
        <Button type="submit" variant="primary" className="h-11">
          Search
        </Button>
      </form>

      <div className="mt-6 space-y-3">
        {!search.data && !hasSources && (
          <EmptyState title="Nothing to search yet" body="Add the Approval Process Handbook to search its clauses here." />
        )}
        {search.data?.length === 0 && <EmptyState title="No matching clauses" body="Try different wording." />}
        {search.data?.map((h) => (
          <article key={h.chunk_id} className="rounded-[var(--radius-panel)] border bg-sheet px-5 py-4">
            <h3 className="font-bold">
              {h.section && `§${h.section} `}
              {h.heading ?? h.source_title}
            </h3>
            <p className="text-sm text-muted">
              {h.source_title} {h.source_version}
              {h.page && `, page ${h.page}`}
            </p>
            <p className="mt-2 line-clamp-6 whitespace-pre-line">{h.text}</p>
          </article>
        ))}
      </div>
    </div>
  );
}
