import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { AppShell } from "./components/layout/AppShell";
import { AuthProvider, useAuth } from "./lib/auth";
import LoginPage from "./pages/LoginPage";
import Dashboard from "./pages/Dashboard";
import ClusterList from "./pages/clusters/ClusterList";
import ClusterDetail from "./pages/clusters/ClusterDetail";
import HardwareAssetList from "./pages/hardware/HardwareAssetList";
import BareMetalHostList from "./pages/hosts/BareMetalHostList";
import DeploymentList from "./pages/deployments/DeploymentList";
import DeploymentDetail from "./pages/deployments/DeploymentDetail";
import AppCatalog from "./pages/catalog/AppCatalog";
import LLMProviders from "./pages/ai/LLMProviders";
import AIWorkloads from "./pages/ai/AIWorkloads";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 5_000 },
  },
});

function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const location = useLocation();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              element={
                <RequireAuth>
                  <AppShell />
                </RequireAuth>
              }
            >
              <Route path="/" element={<Dashboard />} />
              <Route path="/clusters" element={<ClusterList />} />
              <Route path="/clusters/:id" element={<ClusterDetail />} />
              <Route path="/hardware-assets" element={<HardwareAssetList />} />
              <Route path="/baremetal-hosts" element={<BareMetalHostList />} />
              <Route path="/deployments" element={<DeploymentList />} />
              <Route path="/deployments/:id" element={<DeploymentDetail />} />
              <Route path="/app-catalog" element={<AppCatalog />} />
              <Route path="/llm-providers" element={<LLMProviders />} />
              <Route path="/ai-workloads" element={<AIWorkloads />} />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
