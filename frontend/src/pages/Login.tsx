import { useState, type FormEvent } from "react";
import { Navigate } from "react-router";
import { useAuth } from "../auth";
import { Mark } from "../components/Layout";
import { Button, ErrorText, Field, Pill, inputClass } from "../components/ui";

const DEMO_ACCOUNTS = [
  { label: "Institution", email: "institution@wasp.dev" },
  { label: "Reviewer", email: "reviewer@wasp.dev" },
  { label: "Admin", email: "admin@wasp.dev" },
];

export default function Login() {
  const { user, login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (user) return <Navigate to="/" replace />;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
    } catch {
      setError("That email and password don't match an account.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      {/* What the product does, shown with a real finding rather than described. */}
      <section className="hidden flex-col justify-between bg-ink px-14 py-12 text-white lg:flex">
        <div className="flex items-center gap-3">
          <Mark className="size-10 text-[#b9b2f0]" />
          <span className="text-xl font-extrabold tracking-[0.04em]">WASP</span>
        </div>

        <div className="max-w-xl">
          <h1 className="text-[2.6rem] leading-[1.1] font-bold tracking-[-0.02em]">
            Approval scrutiny with the evidence attached.
          </h1>
          <p className="mt-5 max-w-md text-lg leading-relaxed text-white/75">
            Institutions file once. WASP reads every document, checks it against the rules, and
            shows reviewers exactly where each problem is on the page.
          </p>

          <figure className="mt-10 rounded-[var(--radius-panel)] bg-sheet p-5 text-ink shadow-[0_24px_60px_-20px_rgba(0,0,0,0.5)]">
            <div className="flex items-start gap-3">
              <span className="mt-1 size-2.5 shrink-0 rounded-full bg-fail" aria-hidden />
              <div className="min-w-0">
                <p className="font-bold">Every listed faculty member has a matching certificate</p>
                <p className="mt-0.5 text-sm text-muted">
                  3 of 20 listed faculty have no qualification certificate; “Dr. S. Priya” on the
                  faculty list is “S. Priyaa” on her degree.
                </p>
                <div className="mt-3 flex flex-wrap gap-2 text-xs">
                  <span className="rounded border bg-paper px-2 py-1">faculty_list.pdf, page 1</span>
                  <span className="rounded border bg-paper px-2 py-1">certificate_02.pdf, page 1</span>
                  <Pill tone="review">69% read confidence</Pill>
                </div>
              </div>
            </div>
          </figure>
        </div>

        <p className="text-sm text-white/55">Smart India Hackathon 2026, problem statement SIH26262</p>
      </section>

      <section className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-10 flex items-center gap-3 lg:hidden">
            <Mark className="size-9 text-stamp" />
            <span className="text-lg font-extrabold tracking-[0.04em]">WASP</span>
          </div>
          <h2 className="text-2xl font-bold">Sign in</h2>
          <p className="mt-1 text-muted">Use your institution or AICTE account.</p>

          <form onSubmit={onSubmit} className="mt-8 space-y-5">
            <Field label="Email">
              <input
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={inputClass}
              />
            </Field>
            <Field label="Password">
              <input
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={inputClass}
              />
            </Field>
            {error && <ErrorText>{error}</ErrorText>}
            <Button type="submit" variant="primary" disabled={submitting} className="w-full">
              {submitting ? "Signing in…" : "Sign in"}
            </Button>
          </form>

          {import.meta.env.DEV && (
            <div className="mt-10 border-t pt-5">
              <p className="text-sm text-muted">
                Demo accounts, password <span className="font-bold text-ink">wasp1234</span>
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {DEMO_ACCOUNTS.map((a) => (
                  <Button
                    key={a.email}
                    type="button"
                    size="sm"
                    onClick={() => {
                      setEmail(a.email);
                      setPassword("wasp1234");
                    }}
                  >
                    {a.label}
                  </Button>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
