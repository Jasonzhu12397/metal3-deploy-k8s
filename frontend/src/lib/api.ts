import type {
  AddonCatalogItem,
  AddonToggleResult,
  BareMetalHostCreate,
  Cluster,
  ClusterCreate,
  ClusterManifestBundle,
  Deployment,
  HardwareAsset,
  PoolAssignment,
  PoolAssignRequest,
} from "./types";
import { clearSession, getToken, UNAUTHORIZED_EVENT } from "./tokenStore";

const BASE = (import.meta.env.VITE_API_BASE_URL ?? "") + "/api/v1";

class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `HTTP ${status}`;
    super(detail);
    this.status = status;
    this.body = body;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (res.status === 401) {
    // Token missing/expired/revoked -- clear it and let every mounted
    // <AuthProvider> know so the whole app drops back to the login
    // screen, instead of each caller having to check for 401 itself.
    clearSession();
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  }
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      /* empty body */
    }
    throw new ApiError(res.status, body);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (body: unknown) => JSON.stringify(body);

export const api = {
  auth: {
    login: (username: string, password: string) =>
      request<{ access_token: string; token_type: string; username: string }>("/auth/login", {
        method: "POST",
        body: json({ username, password }),
      }),
    me: () => request<{ username: string }>("/auth/me"),
    changePassword: (current_password: string, new_password: string) =>
      request<void>("/auth/change-password", {
        method: "POST",
        body: json({ current_password, new_password }),
      }),
  },

  clusters: {
    list: () => request<Cluster[]>("/clusters"),
    get: (id: string) => request<Cluster>(`/clusters/${id}`),
    create: (body: ClusterCreate) => request<Cluster>("/clusters", { method: "POST", body: json(body) }),
    remove: (id: string) => request<void>(`/clusters/${id}`, { method: "DELETE" }),
    pools: (id: string) => request<Record<string, PoolAssignment[]>>(`/clusters/${id}/pools`),
    assignToPool: (id: string, pool: string, body: PoolAssignRequest) =>
      request<PoolAssignment[]>(`/clusters/${id}/pools/${encodeURIComponent(pool)}/assign`, {
        method: "POST",
        body: json(body),
      }),
    unassignAsset: (id: string, pool: string, assetId: string) =>
      request<void>(`/clusters/${id}/pools/${encodeURIComponent(pool)}/assets/${assetId}`, {
        method: "DELETE",
      }),
    generateManifests: (id: string) =>
      request<ClusterManifestBundle>(`/clusters/${id}/manifests/generate`, { method: "POST" }),
  },

  hardwareAssets: {
    list: (params?: { status?: string; unassigned_only?: boolean; min_memory_gb?: number }) => {
      const qs = new URLSearchParams();
      if (params?.status) qs.set("status", params.status);
      if (params?.unassigned_only) qs.set("unassigned_only", "true");
      if (params?.min_memory_gb) qs.set("min_memory_gb", String(params.min_memory_gb));
      const suffix = qs.toString() ? `?${qs}` : "";
      return request<HardwareAsset[]>(`/hardware-assets${suffix}`);
    },
    get: (id: string) => request<HardwareAsset>(`/hardware-assets/${id}`),
    create: (body: Record<string, unknown>) =>
      request<HardwareAsset>("/hardware-assets", { method: "POST", body: json(body) }),
    update: (id: string, body: Record<string, unknown>) =>
      request<HardwareAsset>(`/hardware-assets/${id}`, { method: "PATCH", body: json(body) }),
    remove: (id: string) => request<void>(`/hardware-assets/${id}`, { method: "DELETE" }),
    syncFromIronic: (id: string, ironicInventory?: Record<string, unknown>) =>
      request<HardwareAsset>(`/hardware-assets/${id}/sync-from-ironic`, {
        method: "POST",
        body: ironicInventory ? json({ ironic_inventory: ironicInventory }) : undefined,
      }),
  },

  addons: {
    catalog: () => request<AddonCatalogItem[]>("/addons/catalog"),
    forCluster: (clusterId: string) => request<AddonCatalogItem[]>(`/clusters/${clusterId}/addons`),
    enable: (clusterId: string, name: string) =>
      request<AddonToggleResult>(`/clusters/${clusterId}/addons/${name}/enable`, { method: "POST" }),
    disable: (clusterId: string, name: string) =>
      request<AddonToggleResult>(`/clusters/${clusterId}/addons/${name}/disable`, { method: "DELETE" }),
  },

  baremetalHosts: {
    list: (nodePool?: string) =>
      request<Record<string, unknown>[]>(`/baremetalhosts${nodePool ? `?node_pool=${nodePool}` : ""}`),
    register: (body: BareMetalHostCreate) =>
      request<{ name: string; applied: boolean }>("/baremetalhosts", { method: "POST", body: json(body) }),
    status: (name: string) => request<Record<string, unknown>>(`/baremetalhosts/${name}/status`),
    setPower: (name: string, online: boolean) =>
      request<{ name: string; online: boolean }>(`/baremetalhosts/${name}/power?online=${online}`, {
        method: "POST",
      }),
  },

  deployments: {
    list: (clusterId?: string) =>
      request<Deployment[]>(`/deployments${clusterId ? `?cluster_id=${clusterId}` : ""}`),
    create: (clusterId: string) =>
      request<Deployment>("/deployments", {
        method: "POST",
        body: json({ cluster_id: clusterId, regenerate_manifests: true }),
      }),
    get: (id: string) => request<Deployment>(`/deployments/${id}`),
  },
};

export { ApiError };
