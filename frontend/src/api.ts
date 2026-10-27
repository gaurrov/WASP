const TOKEN_KEY = "wasp.token";

export type Role = "institution" | "reviewer" | "admin";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  institution_id: string | null;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = tokenStore.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`/api${path}`, { ...init, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, errorMessage(body.detail) ?? res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export function apiJson<T>(path: string, method: string, body: unknown): Promise<T> {
  return api<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// FastAPI returns a string for HTTPException and a list of issues for validation errors.
function errorMessage(detail: unknown): string | undefined {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => `${d.loc?.at(-1) ?? ""}: ${d.msg ?? ""}`)
      .join("; ");
  }
  return undefined;
}

export async function login(email: string, password: string): Promise<void> {
  // OAuth2 password flow expects form-encoded username/password.
  const form = new URLSearchParams({ username: email, password });
  const { access_token } = await api<{ access_token: string }>("/auth/login", {
    method: "POST",
    body: form,
  });
  tokenStore.set(access_token);
}
