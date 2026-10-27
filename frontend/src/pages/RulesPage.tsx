import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { fetchRuleCandidates, fetchRules, humanize, verifyRule, type Rule } from "../applications";
import { useAuth } from "../auth";
import Layout from "../components/Layout";
import { Button, PageHeader, Panel, Pill } from "../components/ui";

function formatParam(value: unknown): string {
  if (Array.isArray(value)) return value.join(" : ");
  return String(value);
}

export default function RulesPage() {
  const { data: rules = [] } = useQuery({ queryKey: ["rules"], queryFn: fetchRules });
  const regulatory = rules.filter((r) => !r.internal);
  const internal = rules.filter((r) => r.internal);
  const unverified = regulatory.filter((r) => r.status !== "approved").length;

  return (
    <Layout>
      <PageHeader
        title="Compliance rules"
        description="The checks run on every submitted application. Rules that encode an AICTE norm stay provisional until someone confirms the norm against the handbook clause."
      />

      <div className="space-y-8">
        <Panel
          title="AICTE norms"
          actions={
            unverified > 0 ? (
              <Pill tone="review">{unverified} not yet verified</Pill>
            ) : (
              <Pill tone="pass">All verified</Pill>
            )
          }
        >
          <ul className="divide-y">
            {regulatory.map((rule) => (
              <RuleRow key={rule.id} rule={rule} />
            ))}
          </ul>
        </Panel>

        <Panel title="Consistency checks">
          <p className="border-b px-5 py-3 text-sm text-muted">
            These compare an application with itself (declared values against documents, documents
            against each other), so they need no regulatory citation.
          </p>
          <ul className="divide-y">
            {internal.map((rule) => (
              <RuleRow key={rule.id} rule={rule} />
            ))}
          </ul>
        </Panel>
      </div>

      <p className="mt-6 text-sm text-muted">
        Rules are defined in <code className="rounded bg-sheet px-1 py-0.5">backend/app/rules/rules.yaml</code>. To
        change a norm, add a new rule version there rather than editing the old one.
      </p>
    </Layout>
  );
}

function RuleRow({ rule }: { rule: Rule }) {
  const [open, setOpen] = useState(false);
  const params = Object.entries(rule.params).filter(([k]) => k !== "label");

  return (
    <li className="px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2.5">
            <h3 className="font-bold">{rule.title}</h3>
            {!rule.internal &&
              (rule.status === "approved" ? (
                <Pill tone="stamp">
                  Verified, §{rule.source_section ?? "—"} page {rule.source_page}
                </Pill>
              ) : (
                <span className="rounded-full border border-dashed border-review/60 px-2 py-0.5 text-xs text-review">
                  Not yet verified
                </span>
              ))}
          </div>
          <p className="mt-0.5 text-sm text-faint">
            {rule.rule_code}, version {rule.version}, {rule.severity} severity
          </p>
          {params.length > 0 && (
            <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm">
              {params.map(([k, v]) => (
                <div key={k} className="flex gap-1.5">
                  <dt className="text-muted">{humanize(k)}</dt>
                  <dd className="font-bold">{formatParam(v)}</dd>
                </div>
              ))}
            </dl>
          )}
          {rule.norm_note && <p className="mt-2 max-w-3xl text-sm text-ink/80">{rule.norm_note}</p>}
        </div>
        {!rule.internal && (
          <Button size="sm" onClick={() => setOpen(!open)} aria-expanded={open}>
            {open ? "Close" : "Find clause"}
          </Button>
        )}
      </div>
      {open && <Candidates rule={rule} />}
    </li>
  );
}

function Candidates({ rule }: { rule: Rule }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const { data: hits, isLoading } = useQuery({
    queryKey: ["rule-candidates", rule.id],
    queryFn: () => fetchRuleCandidates(rule.id),
  });
  const verify = useMutation({
    mutationFn: (chunkId: string) => verifyRule(rule.id, chunkId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["rules"] }),
  });

  if (isLoading) return <p className="mt-4 text-sm text-muted">Searching the handbook…</p>;
  if (!hits?.length) {
    return (
      <p className="mt-4 rounded-[var(--radius-control)] bg-paper px-4 py-3 text-sm">
        No matching passages. Upload the Approval Process Handbook on the{" "}
        <Link to="/handbook" className="font-bold text-stamp underline-offset-2 hover:underline">
          Handbook
        </Link>{" "}
        page first.
      </p>
    );
  }
  return (
    <div className="mt-4 space-y-3">
      <p className="text-sm text-muted">
        Verify only a passage that states the norm above. If the handbook says something different,
        add a new rule version instead.
      </p>
      {hits.map((h) => (
        <div key={h.chunk_id} className="rounded-[var(--radius-control)] border bg-paper/60 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <p className="font-bold">
              {h.source_title} {h.source_version}
              {h.section && `, §${h.section}`}
              {h.heading && ` ${h.heading}`}
              {h.page && `, page ${h.page}`}
            </p>
            {user?.role === "admin" && (
              <Button size="sm" variant="primary" onClick={() => verify.mutate(h.chunk_id)} disabled={verify.isPending}>
                Verify with this clause
              </Button>
            )}
          </div>
          <p className="mt-2 text-sm whitespace-pre-line text-ink/80">{h.text}</p>
          <p className="mt-2 text-xs text-faint">Matched by {h.matched_by.join(" and ")} search</p>
        </div>
      ))}
    </div>
  );
}
