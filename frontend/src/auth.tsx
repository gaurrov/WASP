import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, type ReactNode } from "react";
import { api, login as apiLogin, tokenStore, type User } from "./api";

interface AuthState {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const { data: user, isLoading } = useQuery({
    queryKey: ["me"],
    queryFn: () => api<User | null>("/auth/me"),
    enabled: tokenStore.get() !== null,
    retry: false,
  });

  const login = async (email: string, password: string) => {
    await apiLogin(email, password);
    await queryClient.invalidateQueries({ queryKey: ["me"] });
    await queryClient.fetchQuery({ queryKey: ["me"], queryFn: () => api<User>("/auth/me") });
  };

  const logout = () => {
    tokenStore.clear();
    // Setting (not just clearing) "me" notifies mounted observers so routes re-render.
    queryClient.setQueryData(["me"], null);
    queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
  };

  return (
    <AuthContext.Provider value={{ user: user ?? null, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
