import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import Dashboard from "./pages/Dashboard";
import ClusterList from "./pages/clusters/ClusterList";
import ClusterDetail from "./pages/clusters/ClusterDetail";
import HardwareAssetList from "./pages/hardware/HardwareAssetList";
import BareMetalHostList from "./pages/hosts/BareMetalHostList";
import DeploymentList from "./pages/deployments/DeploymentList";
import DeploymentDetail from "./pages/deployments/DeploymentDetail";
import AppCatalog from "./pages/catalog/AppCatalog";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 5_000 },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/clusters" element={<ClusterList />} />
            <Route path="/clusters/:id" element={<ClusterDetail />} />
            <Route path="/hardware-assets" element={<HardwareAssetList />} />
            <Route path="/baremetal-hosts" element={<BareMetalHostList />} />
            <Route path="/deployments" element={<DeploymentList />} />
            <Route path="/deployments/:id" element={<DeploymentDetail />} />
            <Route path="/app-catalog" element={<AppCatalog />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
