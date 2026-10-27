import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { fetchRuleCandidates, fetchRules, verifyRule, type Rule } from "../applications";
import { useAuth } from "../auth";
import Layout from "../components/Layout";

function RuleStatusBadge({ rule }: { rule: Rule }) {
  if (rule.internal) {
    return <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">internal check</span>;
  }
  if (rule.status === "approved") {
    return (
      <span className="rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-700">
        verified · § {rule.source_section ?? "—"} p. {rule.source_page}
      </span>
    );
  }
  return (
    <span className="rounded border border-dashed border-amber-400 px-1.5 py-0.5 text-xs text-amber-800">
      draft — needs verification
    </span>
  );
}

export default function RulesPage() {
  const { data: rules } = useQuery({ queryKey: ["rules"], queryFn: fetchRules });
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <Layout>
      <h1 className="text-xl font-semibold text-slate-900">Compliance rules</h1>
      <p className="mt-1 max-w-3xl text-sm text-slate-500">
        Internal checks compare an application's own data. Regulatory rules encode an AICTE norm and
        stay <b>draft</b> until an admin confirms the norm against the handbook clause; until then
        their findings are marked provisional. Definitions live in{" "}
        <code className="text-xs">backend/app/rules/rules.yaml</code>.
      </p>

      <ul className="mt-6 divide-y rounded-lg border bg-white">
        {rules?.map((rule) => (
          <li key={rule.id} className="px-4 py-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs text-slate-500">
                  {rule.rule_code} v{rule.version}
                </span>
                <span className="text-sm font-medium text-slate-900">{rule.title}</span>
                <RuleStatusBadge rule={rule} />
              </div>
              {!rule.internal && (
                <button
                  onClick={() => setOpenId(openId === rule.id ? null : rule.id)}
                  className="rounded-md border px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-50"
                >
                  {openId === rule.id ? "Close" : "Find clause"}
                </button>
              )}
            </div>
            {Object.keys(rule.params).length > 0 && (
              <div className="mt-1 font-mono text-xs text-slate-500">
                {Object.entries(rule.params)
                  .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
                  .join("  ")}
              </div>
            )}
            {rule.norm_note && <p className="mt-1 text-xs text-slate-500">{rule.norm_note}</p>}
            {openId === rule.id && <Candidates rule={rule} />}
          </li>
        ))}
      </ul>
    </Layout>
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

  if (isLoading) return <p className="mt-3 text-xs text-slate-500">Searching the handbook…</p>;
  if (!hits?.length) {
    return (
      <p className="mt-3 rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600">
        No matching passages. Upload the APH on the <Link to="/handbook" className="underline">Handbook</Link>{" "}
        page first.
      </p>
    );
  }
  return (
    <div className="mt-3 space-y-2">
      <p className="text-xs text-slate-500">
        Read each passage. Verify only if it states the norm this rule enforces ({" "}
        <span className="font-mono">{JSON.stringify(rule.params)}</span>). If it differs, change{" "}
        <code>rules.yaml</code> (new version) instead.
      </p>
      {hits.map((h) => (
        <div key={h.chunk_id} className="rounded-md border bg-slate-50 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-xs font-medium text-slate-900">
              {h.source_title} {h.source_version}
              {h.section && ` · § ${h.section}`}
              {h.heading && ` ${h.heading}`}
              {h.page && ` · p. ${h.page}`}
              <span className="ml-2 font-normal text-slate-400">matched by {h.matched_by.join(" + ")}</span>
            </div>
            {user?.role === "admin" && (
              <button
                onClick={() => verify.mutate(h.chunk_id)}
                disabled={verify.isPending}
                className="rounded-md bg-slate-900 px-2.5 py-1 text-xs text-white disabled:opacity-50"
              >
                Verify with this clause
              </button>
            )}
          </div>
          <p className="mt-2 whitespace-pre-line text-xs text-slate-700">{h.text}</p>
        </div>
      ))}
    </div>
  );
}
