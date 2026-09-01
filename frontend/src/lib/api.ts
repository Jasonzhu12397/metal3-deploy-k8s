import type {
  AddonCatalogItem,
  AddonToggleResult,
  AIWorkload,
  BareMetalHostCreate,
  Cluster,
  ClusterCreate,
  ClusterManifestBundle,
  Deployment,
  HardwareAsset,
  LLMProviderCredential,
  LLMProviderTestResult,
  PoolAssignment,
  PoolAssignRequest,
} from "./types";
import { clearSession, getToken, UNAUTHORIZED_EVENT } from "./tokenStore";

const BASE = (import.meta.env.VITE_API_BASE_URL ?? "") + "/api/v1";

class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown) {
    super(extractErrorMessage(status, body));
    this.status = status;
    this.body = body;
  }
}

/** FastAPI's `detail` field isn't always a plain string -- Pydantic
 * validation failures (422s) come back as a LIST of {msg, loc, ...}
 * objects, not a string. Blindly doing `String(detail)` on that list
 * produces the literal text "[object Object]" (JS's default Array/Object
 * stringification), which is what actually shipped here until someone
 * hit a real validation error and saw that instead of the message --
 * this handles both shapes properly instead of guessing detail is
 * always a string. */
function extractErrorMessage(status: number, body: unknown): string {
  if (!body || typeof body !== "object" || !("detail" in body)) {
    return `HTTP ${status}`;
  }
  const detail = (body as { detail: unknown }).detail;

  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          const msg = String((item as { msg: unknown }).msg);
          const loc = "loc" in item ? (item as { loc: unknown }).loc : undefined;
          const field = Array.isArray(loc) ? loc.filter((p) => p !== "body").join(".") : "";
          return field ? `${field}: ${msg}` : msg;
        }
        return String(item);
      })
      .filter(Boolean);
    if (messages.length > 0) {
      return messages.join("; ");
    }
  }

  if (typeof detail === "object") {
    // last resort: something structured but not the list-of-{msg} shape
    // above -- still better than "[object Object]"
    try {
      return JSON.stringify(detail);
    } catch {
      return `HTTP ${status}`;
    }
  }

  return `HTTP ${status}`;
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
    list: (params?: { status?: string; unassigned_only?: boolean; min_memory_gb?: number; has_gpu?: boolean }) => {
      const qs = new URLSearchParams();
      if (params?.status) qs.set("status", params.status);
      if (params?.unassigned_only) qs.set("unassigned_only", "true");
      if (params?.min_memory_gb) qs.set("min_memory_gb", String(params.min_memory_gb));
      if (params?.has_gpu !== undefined) qs.set("has_gpu", String(params.has_gpu));
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
    setBmcCredentials: (id: string, username: string, password: string) =>
      request<HardwareAsset>(`/hardware-assets/${id}/bmc-credentials`, {
        method: "POST",
        body: json({ username, password }),
      }),
    resyncBmcSecret: (id: string) =>
      request<{ asset_id: string; secret_name: string; resynced: boolean }>(
        `/hardware-assets/${id}/resync-bmc-secret`,
        { method: "POST" },
      ),
  },

  addons: {
    catalog: () => request<AddonCatalogItem[]>("/addons/catalog"),
    forCluster: (clusterId: string) => request<AddonCatalogItem[]>(`/clusters/${clusterId}/addons`),
    enable: (clusterId: string, name: string) =>
      request<AddonToggleResult>(`/clusters/${clusterId}/addons/${name}/enable`, { method: "POST" }),
    disable: (clusterId: string, name: string) =>
      request<AddonToggleResult>(`/clusters/${clusterId}/addons/${name}/disable`, { method: "DELETE" }),
  },

  llmProviders: {
    list: () => request<LLMProviderCredential[]>("/llm-providers"),
    create: (body: {
      label: string;
      provider: string;
      api_key: string;
      base_url?: string;
      default_model?: string;
    }) => request<LLMProviderCredential>("/llm-providers", { method: "POST", body: json(body) }),
    remove: (id: string) => request<void>(`/llm-providers/${id}`, { method: "DELETE" }),
    testConnection: (id: string) =>
      request<LLMProviderTestResult>(`/llm-providers/${id}/test-connection`, { method: "POST" }),
  },

  aiWorkloads: {
    list: (clusterId?: string) =>
      request<AIWorkload[]>(`/ai-workloads${clusterId ? `?cluster_id=${clusterId}` : ""}`),
    create: (body: {
      name: string;
      cluster_id: string;
      namespace?: string;
      model_id: string;
      gpu_count?: number;
      replicas?: number;
      image_tag?: string;
      extra_args?: string[];
      hf_token_secret_name?: string;
    }) => request<AIWorkload>("/ai-workloads", { method: "POST", body: json(body) }),
    redeploy: (id: string) => request<AIWorkload>(`/ai-workloads/${id}/redeploy`, { method: "POST" }),
    remove: (id: string) => request<void>(`/ai-workloads/${id}`, { method: "DELETE" }),
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
