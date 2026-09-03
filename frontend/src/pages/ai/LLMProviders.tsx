import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Cpu, Plus, X, Zap } from "lucide-react";
import { useState } from "react";
import { api, ApiError } from "../../lib/api";
import { EmptyState } from "../../components/ui/EmptyState";
import type { LLMProviderKind } from "../../lib/types";
import { useLanguage } from "../../lib/i18n";

type TranslationKey = Parameters<ReturnType<typeof useLanguage>["t"]>[0];

const PROVIDERS: { value: LLMProviderKind; labelKey: TranslationKey; hint: string }[] = [
  { value: "openai", labelKey: "llm.providerOpenAI" as TranslationKey, hint: "https://api.openai.com/v1" },
  { value: "deepseek", labelKey: "llm.providerDeepSeek" as TranslationKey, hint: "https://api.deepseek.com/v1" },
  { value: "qwen", labelKey: "llm.providerQwen", hint: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
  { value: "doubao", labelKey: "llm.providerDoubao", hint: "https://ark.cn-beijing.volces.com/api/v3" },
  { value: "custom", labelKey: "llm.providerCustom", hint: "llm.providerCustomHint" },
];

export default function LLMProviders() {
  const { t } = useLanguage();
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
        <p className="text-xs text-[var(--color-ink-muted)]">{t("llm.hint")}</p>
        <button className="btn btn-primary shrink-0" onClick={() => setShowCreate(true)}>
          <Plus size={14} /> {t("llm.addCredential")}
        </button>
      </div>

      {isLoading ? (
        <p className="text-xs text-[var(--color-ink-faint)]">{t("llm.loading")}</p>
      ) : !providers || providers.length === 0 ? (
        <div className="card">
          <EmptyState icon={Zap} title={t("llm.emptyTitle")} hint={t("llm.emptyHint")} />
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
  const { t } = useLanguage();
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
            <span className="text-[11px] text-[var(--color-ink-faint)]">{providerMeta ? t(providerMeta.labelKey) : provider.provider}</span>
          </div>
        </div>
        <button
          onClick={onDelete}
          className="flex h-6 w-6 items-center justify-center rounded-md text-[var(--color-ink-faint)] hover:bg-[var(--color-danger-soft)] hover:text-[var(--color-danger)]"
          title={t("llm.delete")}
        >
          <X size={14} />
        </button>
      </div>

      <p className="mono truncate text-[11px] text-[var(--color-ink-faint)]" title={provider.base_url}>
        {provider.base_url}
      </p>
      {provider.default_model && (
        <p className="text-[11px] text-[var(--color-ink-muted)]">{t("llm.defaultModel", { model: provider.default_model })}</p>
      )}

      <button
        className="btn btn-secondary mt-1"
        onClick={() => testMutation.mutate()}
        disabled={testMutation.isPending}
      >
        {testMutation.isPending ? t("llm.testing") : t("llm.testConnection")}
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
              ? `${t("llm.connectionOk", { latency: "" })}${testMutation.data.latency_ms ? t("llm.latencyMs", { ms: testMutation.data.latency_ms }) : ""}`
              : testMutation.data.error}
          </span>
        </div>
      )}
    </div>
  );
}

function CreateProviderModal({ onClose }: { onClose: () => void }) {
  const { t } = useLanguage();
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
    onError: (e: Error) => setError(e instanceof ApiError ? e.message : t("llm.createFailed")),
  });

  const isCustom = provider === "custom";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-xl bg-[var(--color-surface)] p-5 shadow-xl">
        <h3 className="mb-3 text-sm font-bold">{t("llm.modalTitle")}</h3>
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            createMutation.mutate();
          }}
        >
          <div>
            <label className="label">{t("llm.labelField")}</label>
            <input
              className="input"
              required
              placeholder="prod-openai-key"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
          </div>

          <div>
            <label className="label">{t("llm.vendor")}</label>
            <select className="input" value={provider} onChange={(e) => setProvider(e.target.value as LLMProviderKind)}>
              {PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>
                  {t(p.labelKey)}
                </option>
              ))}
            </select>
            {!isCustom && (
              <p className="mt-1 text-[10px] text-[var(--color-ink-faint)]">
                {t("llm.defaultBaseUrl", { url: PROVIDERS.find((p) => p.value === provider)?.hint ?? "" })}
              </p>
            )}
          </div>

          <div>
            <label className="label">Base URL {isCustom && <span className="text-[var(--color-danger)]">*</span>}</label>
            <input
              className="input mono"
              required={isCustom}
              placeholder={isCustom ? "https://your-endpoint/v1" : t("llm.baseUrlPlaceholder")}
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
            />
          </div>

          <div>
            <label className="label">{t("llm.defaultModelField")}</label>
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
            <p className="mt-1 text-[10px] text-[var(--color-ink-faint)]">{t("llm.apiKeySavedHint")}</p>
          </div>

          {error && <p className="text-xs text-[var(--color-danger)]">{error}</p>}

          <div className="mt-1 flex justify-end gap-2">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              {t("llm.cancel")}
            </button>
            <button type="submit" className="btn btn-primary" disabled={createMutation.isPending}>
              {createMutation.isPending ? t("llm.creating") : t("llm.create")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
