import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { createApplication, fetchApplicationTypes } from "../applications";
import Layout from "../components/Layout";

function defaultAcademicYear(): string {
  const y = new Date().getFullYear();
  return `${y}-${String((y + 1) % 100).padStart(2, "0")}`;
}

const inputClass = "mt-1 w-full rounded-md border px-3 py-2 text-sm";

export default function NewApplication() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: types } = useQuery({
    queryKey: ["application-types"],
    queryFn: fetchApplicationTypes,
  });

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

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate({
      application_type: type || types![0].code,
      academic_year: academicYear,
      declared: {
        programme,
        sanctioned_intake: Number(intake),
        faculty_count: Number(faculty),
      },
    });
  };

  return (
    <Layout>
      <h1 className="text-xl font-semibold text-slate-900">New application</h1>
      <form onSubmit={onSubmit} className="mt-6 max-w-xl space-y-4 rounded-lg border bg-white p-6">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Application type</span>
            <select value={type} onChange={(e) => setType(e.target.value)} className={inputClass}>
              {types?.map((t) => (
                <option key={t.code} value={t.code}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Academic year</span>
            <input
              required
              pattern="\d{4}-\d{2}"
              placeholder="2026-27"
              value={academicYear}
              onChange={(e) => setAcademicYear(e.target.value)}
              className={inputClass}
            />
          </label>
        </div>

        <fieldset className="space-y-4 border-t pt-4">
          <legend className="text-sm font-medium text-slate-900">Declared values</legend>
          <p className="text-xs text-slate-500">
            These are checked against your uploaded documents during review.
          </p>
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Programme</span>
            <input
              required
              placeholder="B.E. Computer Science and Engineering"
              value={programme}
              onChange={(e) => setProgramme(e.target.value)}
              className={inputClass}
            />
          </label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="text-sm font-medium text-slate-700">Sanctioned intake</span>
              <input
                required
                type="number"
                min={0}
                value={intake}
                onChange={(e) => setIntake(e.target.value)}
                className={inputClass}
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-slate-700">Faculty count</span>
              <input
                required
                type="number"
                min={0}
                value={faculty}
                onChange={(e) => setFaculty(e.target.value)}
                className={inputClass}
              />
            </label>
          </div>
        </fieldset>

        {create.error && <p className="text-sm text-red-600">{create.error.message}</p>}
        <button
          type="submit"
          disabled={!types || create.isPending}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {create.isPending ? "Creating…" : "Create draft"}
        </button>
      </form>
    </Layout>
  );
}
