import { useState, type FormEvent } from "react";
import { Navigate } from "react-router";
import { useAuth } from "../auth";

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
      setError("Invalid email or password.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-sm">
        <h1 className="text-2xl font-semibold text-slate-900">WASP</h1>
        <p className="mt-1 text-sm text-slate-500">
          Workflow Automation System Project — AICTE approvals & compliance
        </p>

        <form onSubmit={onSubmit} className="mt-8 space-y-4 rounded-lg border bg-white p-6">
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Email</span>
            <input
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Password</span>
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
            />
          </label>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md bg-slate-900 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>

        {import.meta.env.DEV && (
          <div className="mt-4 text-xs text-slate-500">
            Demo accounts (password <code>wasp1234</code>):
            <div className="mt-2 flex gap-2">
              {DEMO_ACCOUNTS.map((a) => (
                <button
                  key={a.email}
                  type="button"
                  onClick={() => {
                    setEmail(a.email);
                    setPassword("wasp1234");
                  }}
                  className="rounded border bg-white px-2 py-1 hover:bg-slate-100"
                >
                  {a.label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
