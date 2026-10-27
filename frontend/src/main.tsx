import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { AuthProvider, useAuth } from "./auth";
import "./index.css";
import ApplicationDetail from "./pages/ApplicationDetail";
import ApplicationsList from "./pages/ApplicationsList";
import Dashboard from "./pages/Dashboard";
import DocumentViewer from "./pages/DocumentViewer";
import Login from "./pages/Login";
import NewApplication from "./pages/NewApplication";

const queryClient = new QueryClient();

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuth();
  if (isLoading) return null;
  return user ? children : <Navigate to="/login" replace />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={<RequireAuth><Dashboard /></RequireAuth>} />
            <Route path="/applications" element={<RequireAuth><ApplicationsList /></RequireAuth>} />
            <Route path="/applications/new" element={<RequireAuth><NewApplication /></RequireAuth>} />
            <Route path="/applications/:id" element={<RequireAuth><ApplicationDetail /></RequireAuth>} />
            <Route path="/documents/:id" element={<RequireAuth><DocumentViewer /></RequireAuth>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
