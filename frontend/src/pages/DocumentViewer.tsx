import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import {
  fetchDocument,
  fetchPageImage,
  humanize,
  isProcessing,
  openDocument,
  reprocessDocument,
  type DocumentDetail,
  type Fact,
} from "../applications";
import { useAuth } from "../auth";
import Layout from "../components/Layout";

function formatValue(value: unknown): string {
  if (value && typeof value === "object") return Object.values(value).join(" · ");
  return String(value);
}

function ConfidenceBadge({ fact }: { fact: Fact }) {
  const pct = Math.round(fact.confidence * 100);
  const style = fact.low_confidence
    ? "bg-amber-100 text-amber-900"
    : "bg-emerald-50 text-emerald-700";
  return <span className={`rounded px-1.5 py-0.5 text-[11px] tabular-nums ${style}`}>{pct}%</span>;
}

export default function DocumentViewer() {
  const { id = "" } = useParams();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  // Evidence links from findings open the viewer with that fact preselected.
  const [selected, setSelected] = useState<string | null>(searchParams.get("fact"));

  const { data: doc, error } = useQuery({
    queryKey: ["document", id],
    queryFn: () => fetchDocument(id),
    refetchInterval: (q) => (q.state.data && isProcessing(q.state.data.processing_status) ? 1500 : false),
  });

  const reprocess = useMutation({
    mutationFn: () => reprocessDocument(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["document", id] }),
  });

  if (error) {
    return (
      <Layout>
        <p className="text-sm text-red-600">{error.message}</p>
      </Layout>
    );
  }
  if (!doc) return <Layout>Loading…</Layout>;

  const canReprocess = user?.role === "reviewer" || user?.role === "admin";
  const lowCount = doc.facts.filter((f) => f.low_confidence).length;

  return (
    <Layout>
      <Link
        to={`/applications/${doc.application_id}`}
        className="text-sm text-slate-500 hover:text-slate-900"
      >
        ← Application
      </Link>

      <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">{doc.filename}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-500">
            <span>Declared: {humanize(doc.doc_type)}</span>
            {doc.detected_doc_type && (
              <span>
                · Detected: {humanize(doc.detected_doc_type)} (
                {Math.round((doc.detection_confidence ?? 0) * 100)}%)
              </span>
            )}
            {doc.ocr_used && (
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">OCR</span>
            )}
            <span>· v{doc.version}</span>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => openDocument(doc.id)}
            className="rounded-md border bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
          >
            Open original
          </button>
          {canReprocess && (
            <button
              onClick={() => reprocess.mutate()}
              disabled={reprocess.isPending || isProcessing(doc.processing_status)}
              className="rounded-md border bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              Re-run extraction
            </button>
          )}
        </div>
      </div>

      {doc.type_mismatch && (
        <p className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          This file was uploaded as <b>{humanize(doc.doc_type)}</b> but looks like a{" "}
          <b>{humanize(doc.detected_doc_type!)}</b>. Fields were extracted for the declared type.
        </p>
      )}
      {doc.processing_status === "failed" && (
        <p className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          Extraction failed: {doc.processing_error}
        </p>
      )}

      {isProcessing(doc.processing_status) ? (
        <p className="mt-8 text-sm text-slate-500">Extracting text and fields…</p>
      ) : (
        <div className="mt-6 grid gap-6 lg:grid-cols-[22rem_1fr]">
          <section className="h-fit rounded-lg border bg-white lg:sticky lg:top-4">
            <div className="flex items-center justify-between border-b px-4 py-3">
              <h2 className="text-sm font-medium text-slate-900">Extracted fields</h2>
              {lowCount > 0 && (
                <span className="text-xs text-amber-800">{lowCount} to verify</span>
              )}
            </div>
            {doc.facts.length === 0 ? (
              <p className="px-4 py-6 text-sm text-slate-500">No fields extracted.</p>
            ) : (
              <ul className="max-h-[70vh] divide-y overflow-y-auto">
                {doc.facts.map((f) => (
                  <li key={f.id}>
                    <button
                      onClick={() => setSelected(f.id === selected ? null : f.id)}
                      className={`w-full px-4 py-2.5 text-left hover:bg-slate-50 ${
                        f.id === selected ? "bg-blue-50" : ""
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs text-slate-500">{humanize(f.field_name)}</span>
                        <ConfidenceBadge fact={f} />
                      </div>
                      <div className="mt-0.5 text-sm text-slate-900">{formatValue(f.value)}</div>
                      {f.raw_text && f.raw_text !== String(f.value) && f.low_confidence && (
                        <div className="mt-0.5 text-xs text-slate-400">read as “{f.raw_text}”</div>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="space-y-4">
            {doc.pages.map((p) => (
              <PageImage
                key={p.number}
                doc={doc}
                page={p}
                facts={doc.facts.filter((f) => f.page === p.number && f.bbox)}
                selected={selected}
                onSelect={setSelected}
              />
            ))}
          </section>
        </div>
      )}
    </Layout>
  );
}

function PageImage({
  doc,
  page,
  facts,
  selected,
  onSelect,
}: {
  doc: DocumentDetail;
  page: DocumentDetail["pages"][number];
  facts: Fact[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const [src, setSrc] = useState<string | null>(null);
  const selectedRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let url: string | null = null;
    fetchPageImage(doc.id, page.number).then((u) => {
      url = u;
      setSrc(u);
    });
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [doc.id, doc.processed_at, page.number]);

  useEffect(() => {
    selectedRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [selected]);

  // Boxes are positioned in percentages of the page, so they track the image at any width.
  const pct = (v: number, of: number) => `${(v / of) * 100}%`;

  return (
    <div className="relative overflow-hidden rounded-lg border bg-white shadow-sm">
      {src ? (
        <img src={src} alt={`Page ${page.number}`} className="block w-full" />
      ) : (
        <div style={{ aspectRatio: `${page.width} / ${page.height}` }} className="bg-slate-100" />
      )}
      {facts.map((f) => {
        const [x0, y0, x1, y1] = f.bbox!;
        const active = f.id === selected;
        const color = f.low_confidence
          ? "border-amber-500 bg-amber-300/25"
          : "border-blue-500 bg-blue-300/15";
        return (
          <button
            key={f.id}
            ref={active ? selectedRef : undefined}
            title={`${humanize(f.field_name)}: ${formatValue(f.value)}`}
            onClick={() => onSelect(f.id)}
            className={`absolute rounded-sm border ${color} ${active ? "ring-2 ring-blue-600 ring-offset-1" : "opacity-70 hover:opacity-100"}`}
            style={{
              left: pct(x0 - 2, page.width),
              top: pct(y0 - 2, page.height),
              width: pct(x1 - x0 + 4, page.width),
              height: pct(y1 - y0 + 4, page.height),
            }}
          />
        );
      })}
      <span className="absolute right-2 top-2 rounded bg-white/80 px-1.5 text-xs text-slate-500">
        Page {page.number}
        {page.ocr && " · OCR"}
      </span>
    </div>
  );
}
