import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { createApplication, fetchApplicationTypes } from "../applications";
import Layout from "../components/Layout";
import { Button, ErrorText, Field, PageHeader, Panel, inputClass } from "../components/ui";

function defaultAcademicYear(): string {
  const y = new Date().getFullYear();
  return `${y}-${String((y + 1) % 100).padStart(2, "0")}`;
}

export default function NewApplication() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: types } = useQuery({ queryKey: ["application-types"], queryFn: fetchApplicationTypes });

  const [type, setType] = useState("");
  const [academicYear, setAcademicYear] = useState(defaultAcademicYear);
  const [programme, setProgramme] = useState("");
  const [intake, setIntake] = useState("");
  const [faculty, setFaculty] = useState("");

  const create = useMutation({
    mutationFn: createApplication,
    onSuccess: (app) => {
      queryClient.invalidateQueries({ queryKey: ["applications"] });
      navigate(`/applications/${app.id}`);
    },
  });

  const selected = types?.find((t) => t.code === (type || types[0]?.code));

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate({
      application_type: selected!.code,
      academic_year: academicYear,
      declared: { programme, sanctioned_intake: Number(intake), faculty_count: Number(faculty) },
    });
  };

  return (
    <Layout>
      <PageHeader
        back={{ to: "/applications", label: "Applications" }}
        title="New application"
        description="Create a draft first. You'll upload documents on the next page and submit when ready."
      />

      <div className="grid items-start gap-8 lg:grid-cols-[1fr_20rem]">
        <form onSubmit={onSubmit}>
          <Panel title="Application">
            <div className="grid gap-5 px-5 py-5 sm:grid-cols-2">
              <Field label="Type">
                <select value={type} onChange={(e) => setType(e.target.value)} className={inputClass}>
                  {types?.map((t) => (
                    <option key={t.code} value={t.code}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Academic year" hint="For example 2026-27">
                <input
                  required
                  pattern="\d{4}-\d{2}"
                  value={academicYear}
                  onChange={(e) => setAcademicYear(e.target.value)}
                  className={inputClass}
                />
              </Field>
            </div>
            <div className="border-t px-5 py-5">
              <h3 className="font-bold">What you're declaring</h3>
              <p className="mt-0.5 text-sm text-muted">
                These are checked against your documents, so they should match your faculty list
                and approval letters.
              </p>
              <div className="mt-5 grid gap-5 sm:grid-cols-2">
                <div className="sm:col-span-2">
                  <Field label="Programme">
                    <input
                      required
                      placeholder="B.E. Computer Science and Engineering"
                      value={programme}
                      onChange={(e) => setProgramme(e.target.value)}
                      className={inputClass}
                    />
                  </Field>
                </div>
                <Field label="Sanctioned intake" hint="Students admitted per year">
                  <input
                    required
                    type="number"
                    min={0}
                    value={intake}
                    onChange={(e) => setIntake(e.target.value)}
                    className={inputClass}
                  />
                </Field>
                <Field label="Faculty count" hint="As on your faculty list">
                  <input
                    required
                    type="number"
                    min={0}
                    value={faculty}
                    onChange={(e) => setFaculty(e.target.value)}
                    className={inputClass}
                  />
                </Field>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-3 border-t px-5 py-4">
              <Button type="submit" variant="primary" disabled={!types || create.isPending}>
                {create.isPending ? "Creating draft…" : "Create draft"}
              </Button>
              {create.error && <ErrorText>{create.error.message}</ErrorText>}
            </div>
          </Panel>
        </form>

        {selected && (
          <Panel title="Documents you'll need">
            <ul className="space-y-2 px-5 py-4 text-sm">
              {selected.checklist.map((c) => (
                <li key={c.doc_type} className="flex justify-between gap-3">
                  <span>{c.label}</span>
                  {!c.required && <span className="text-muted">optional</span>}
                </li>
              ))}
            </ul>
          </Panel>
        )}
      </div>
    </Layout>
  );
}
