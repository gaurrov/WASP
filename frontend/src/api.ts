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
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
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
