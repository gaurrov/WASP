import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, RotateCcw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router";
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
import { Button, ErrorText, Notice, PageHeader, Panel, Pill, formatValue } from "../components/ui";

export default function DocumentViewer() {
  const { id = "" } = useParams();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  // Evidence links from findings open the viewer with that value preselected.
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
        <ErrorText>{error.message}</ErrorText>
      </Layout>
    );
  }
  if (!doc) return <Layout>Loading document…</Layout>;

  const canReprocess = user?.role === "reviewer" || user?.role === "admin";
  const lowCount = doc.facts.filter((f) => f.low_confidence).length;

  return (
    <Layout>
      <PageHeader
        back={{ to: `/applications/${doc.application_id}`, label: "Back to application" }}
        title={doc.filename}
        description={
          <>
            {humanize(doc.doc_type)}, version {doc.version}
            {doc.ocr_used && ", read with OCR from a scan"}
            {doc.detected_doc_type && doc.detected_doc_type !== doc.doc_type && (
              <>. Content looks like a {humanize(doc.detected_doc_type).toLowerCase()}</>
            )}
          </>
        }
        actions={
          <>
            <Button onClick={() => openDocument(doc.id)}>
              <ExternalLink size={15} aria-hidden />
              Open original
            </Button>
            {canReprocess && (
              <Button
                onClick={() => reprocess.mutate()}
                disabled={reprocess.isPending || isProcessing(doc.processing_status)}
              >
                <RotateCcw size={15} aria-hidden />
                Read again
              </Button>
            )}
          </>
        }
      />

      <div className="space-y-4">
        {doc.type_mismatch && (
          <Notice tone="review" title="This may be the wrong document">
            It was uploaded as a {humanize(doc.doc_type).toLowerCase()}, but its content looks like a{" "}
            {humanize(doc.detected_doc_type!).toLowerCase()}. Fields were read for the type it was uploaded as.
          </Notice>
        )}
        {doc.processing_status === "failed" && (
          <Notice tone="fail" title="This document couldn't be read">
            {doc.processing_error}
          </Notice>
        )}
      </div>

      {isProcessing(doc.processing_status) ? (
        <p className="mt-8 text-muted">Reading text and fields…</p>
      ) : (
        <div className="mt-6 grid items-start gap-8 lg:grid-cols-[22rem_minmax(0,1fr)]">
          <Panel
            title="Values read from this document"
            actions={lowCount > 0 && <Pill tone="review">{lowCount} to verify</Pill>}
            className="lg:sticky lg:top-8"
          >
            {doc.facts.length === 0 ? (
              <p className="px-5 py-6 text-sm text-muted">No values could be read from this document.</p>
            ) : (
              <ul className="max-h-[70vh] divide-y overflow-y-auto">
                {doc.facts.map((f) => (
                  <li key={f.id}>
                    <button
                      onClick={() => setSelected(f.id === selected ? null : f.id)}
                      aria-pressed={f.id === selected}
                      className={`w-full border-l-[3px] px-5 py-3 text-left transition-colors ${
                        f.id === selected ? "border-stamp bg-stamp-soft" : "border-transparent hover:bg-paper/70"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm text-muted">{humanize(f.field_name)}</span>
                        <span className={`text-sm font-bold ${f.low_confidence ? "text-review" : "text-pass"}`}>
                          {Math.round(f.confidence * 100)}%
                        </span>
                      </div>
                      <div className="mt-0.5 font-bold">{formatValue(f.value)}</div>
                      {f.raw_text && f.raw_text !== String(f.value) && f.low_confidence && (
                        <div className="mt-0.5 text-sm text-muted">Read as “{f.raw_text}”</div>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <div className="space-y-6 rounded-[var(--radius-panel)] bg-[#e4e8ee] p-4 sm:p-6">
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
          </div>
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
    <figure className="mx-auto max-w-[52rem]">
      <div className="relative overflow-hidden bg-sheet shadow-[0_1px_3px_rgba(24,38,61,0.12),0_12px_32px_-12px_rgba(24,38,61,0.25)]">
        {src ? (
          <img src={src} alt={`Page ${page.number} of ${doc.filename}`} className="block w-full" />
        ) : (
          <div style={{ aspectRatio: `${page.width} / ${page.height}` }} className="bg-sheet" />
        )}
        {facts.map((f) => {
          const [x0, y0, x1, y1] = f.bbox!;
          const active = f.id === selected;
          const tone = f.low_confidence ? "border-review bg-review/15" : "border-stamp/70 bg-stamp/10";
          return (
            <button
              key={f.id}
              ref={active ? selectedRef : undefined}
              aria-label={`${humanize(f.field_name)}: ${formatValue(f.value)}`}
              title={`${humanize(f.field_name)}: ${formatValue(f.value)}`}
              onClick={() => onSelect(f.id)}
              className={`absolute rounded-[3px] border ${
                active ? "border-2 border-stamp bg-stamp/15 ring-4 ring-stamp/20" : `${tone} opacity-75 hover:opacity-100`
              }`}
              style={{
                left: pct(x0 - 2, page.width),
                top: pct(y0 - 2, page.height),
                width: pct(x1 - x0 + 4, page.width),
                height: pct(y1 - y0 + 4, page.height),
              }}
            />
          );
        })}
      </div>
      <figcaption className="mt-2 text-center text-sm text-muted">
        Page {page.number}
        {page.ocr && ", read with OCR"}
      </figcaption>
    </figure>
  );
}
