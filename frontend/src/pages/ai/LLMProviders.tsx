import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Cpu, Plus, X, Zap } from "lucide-react";
import { useState } from "react";
import { api, ApiError } from "../../lib/api";
import { EmptyState } from "../../components/ui/EmptyState";
import type { LLMProviderKind } from "../../lib/types";

const PROVIDERS: { value: LLMProviderKind; label: string; hint: string }[] = [
  { value: "openai", label: "OpenAI (ChatGPT)", hint: "https://api.openai.com/v1" },
  { value: "deepseek", label: "DeepSeek", hint: "https://api.deepseek.com/v1" },
  { value: "qwen", label: "通义千问 (DashScope)", hint: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
  { value: "doubao", label: "豆包 (火山方舟 Ark)", hint: "https://ark.cn-beijing.volces.com/api/v3" },
  { value: "custom", label: "自定义 OpenAI 兼容端点", hint: "需要自己填 Base URL" },
];

export default function LLMProviders() {
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);

  const { data: providers, isLoading } = useQuery({
    queryKey: ["llm-providers"],
    queryFn: api.llmProviders.list,
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) => api.llmProviders.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["llm-providers"] }),
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-[var(--color-ink-muted)]">
          管理外部大模型 API 凭证（OpenAI/DeepSeek/通义千问/豆包，或任何 OpenAI 兼容端点）。密钥加密存储，接口不会把密钥明文或密文返回——跟 BMC 密码用的是同一套加密机制。
        </p>
        <button className="btn btn-primary shrink-0" onClick={() => setShowCreate(true)}>
          <Plus size={14} /> 添加凭证
        </button>
      </div>

      {isLoading ? (
        <p className="text-xs text-[var(--color-ink-faint)]">加载中...</p>
      ) : !providers || providers.length === 0 ? (
        <div className="card">
          <EmptyState icon={Zap} title="还没有配置任何 LLM 凭证" hint="点右上角「添加凭证」接入外部大模型 API" />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {providers.map((p) => (
            <ProviderCard key={p.id} provider={p} onDelete={() => removeMutation.mutate(p.id)} />
          ))}
        </div>
      )}

      {showCreate && <CreateProviderModal onClose={() => setShowCreate(false)} />}
    </div>
  );
}

function ProviderCard({
  provider,
  onDelete,
}: {
  provider: { id: string; label: string; provider: LLMProviderKind; base_url: string; default_model: string | null };
  onDelete: () => void;
}) {
  const testMutation = useMutation({
    mutationFn: () => api.llmProviders.testConnection(provider.id),
  });
  const providerMeta = PROVIDERS.find((p) => p.value === provider.provider);

  return (
    <div className="card flex flex-col gap-3 p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--color-navy-900)] text-white">
            <Cpu size={16} />
          </div>
          <div>
            <div className="text-sm font-bold leading-tight">{provider.label}</div>
            <span className="text-[11px] text-[var(--color-ink-faint)]">{providerMeta?.label ?? provider.provider}</span>
          </div>
        </div>
        <button
          onClick={onDelete}
          className="flex h-6 w-6 items-center justify-center rounded-md text-[var(--color-ink-faint)] hover:bg-[var(--color-danger-soft)] hover:text-[var(--color-danger)]"
          title="删除"
        >
          <X size={14} />
        </button>
      </div>

      <p className="mono truncate text-[11px] text-[var(--color-ink-faint)]" title={provider.base_url}>
        {provider.base_url}
      </p>
      {provider.default_model && (
        <p className="text-[11px] text-[var(--color-ink-muted)]">默认模型：{provider.default_model}</p>
      )}

      <button
        className="btn btn-secondary mt-1"
        onClick={() => testMutation.mutate()}
        disabled={testMutation.isPending}
      >
        {testMutation.isPending ? "测试中..." : "测试连通性"}
      </button>

      {testMutation.data && (
        <div
          className={`flex items-start gap-1.5 rounded-lg px-2.5 py-2 text-[11px] ${
            testMutation.data.ok
              ? "bg-[var(--color-success-soft)] text-[var(--color-success)]"
              : "bg-[var(--color-danger-soft)] text-[var(--color-danger)]"
          }`}
        >
          {testMutation.data.ok ? <Check size={13} className="mt-0.5 shrink-0" /> : <X size={13} className="mt-0.5 shrink-0" />}
          <span>
            {testMutation.data.ok
              ? `连通正常${testMutation.data.latency_ms ? `（${testMutation.data.latency_ms}ms）` : ""}`
              : testMutation.data.error}
          </span>
        </div>
      )}
    </div>
  );
}

function CreateProviderModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [label, setLabel] = useState("");
  const [provider, setProvider] = useState<LLMProviderKind>("openai");
  const [baseUrl, setBaseUrl] = useState("");
  const [defaultModel, setDefaultModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: () =>
      api.llmProviders.create({
        label,
        provider,
        api_key: apiKey,
        base_url: baseUrl || undefined,
        default_model: defaultModel || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["llm-providers"] });
      onClose();
    },
    onError: (e: Error) => setError(e instanceof ApiError ? e.message : "创建失败"),
  });

  const isCustom = provider === "custom";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-xl bg-[var(--color-surface)] p-5 shadow-xl">
        <h3 className="mb-3 text-sm font-bold">添加 LLM 凭证</h3>
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            createMutation.mutate();
          }}
        >
          <div>
            <label className="label">名称（自己起的，方便区分）</label>
            <input
              className="input"
              required
              placeholder="prod-openai-key"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
          </div>

          <div>
            <label className="label">厂商</label>
            <select className="input" value={provider} onChange={(e) => setProvider(e.target.value as LLMProviderKind)}>
              {PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
            {!isCustom && (
              <p className="mt-1 text-[10px] text-[var(--color-ink-faint)]">
                默认 Base URL：{PROVIDERS.find((p) => p.value === provider)?.hint}
              </p>
            )}
          </div>

          <div>
            <label className="label">Base URL {isCustom && <span className="text-[var(--color-danger)]">*</span>}</label>
            <input
              className="input mono"
              required={isCustom}
              placeholder={isCustom ? "https://your-endpoint/v1" : "留空用默认值"}
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
            />
          </div>

          <div>
            <label className="label">默认模型（可选，测试连通性时用）</label>
            <input
              className="input mono"
              placeholder="gpt-4o-mini / deepseek-chat / qwen-plus ..."
              value={defaultModel}
              onChange={(e) => setDefaultModel(e.target.value)}
            />
          </div>

          <div>
            <label className="label">API Key</label>
            <input
              className="input mono"
              type="password"
              required
              placeholder="sk-..."
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
            <p className="mt-1 text-[10px] text-[var(--color-ink-faint)]">
              提交后立刻加密存库；密钥本身不会再被任何接口返回。
            </p>
          </div>

          {error && <p className="text-xs text-[var(--color-danger)]">{error}</p>}

          <div className="mt-1 flex justify-end gap-2">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              取消
            </button>
            <button type="submit" className="btn btn-primary" disabled={createMutation.isPending}>
              {createMutation.isPending ? "创建中..." : "创建"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
