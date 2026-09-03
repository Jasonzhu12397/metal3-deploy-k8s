import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Power, PowerOff, Server } from "lucide-react";
import { useState } from "react";
import { api } from "../../lib/api";
import { useLanguage } from "../../lib/i18n";
import { EmptyState } from "../../components/ui/EmptyState";
import { Modal } from "../../components/ui/Modal";
import type { BareMetalHostCreate } from "../../lib/types";

export default function BareMetalHostList() {
  const { t } = useLanguage();
  const qc = useQueryClient();
  const [showRegister, setShowRegister] = useState(false);
  const { data: hosts, isLoading } = useQuery({
    queryKey: ["baremetal-hosts"],
    queryFn: () => api.baremetalHosts.list(),
  });

  const powerMutation = useMutation({
    mutationFn: ({ name, online }: { name: string; online: boolean }) =>
      api.baremetalHosts.setPower(name, online),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["baremetal-hosts"] }),
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-[var(--color-ink-muted)]">{t("bmh.hint")}</p>
        <button className="btn btn-primary" onClick={() => setShowRegister(true)}>
          <Plus size={14} /> {t("bmh.register")}
        </button>
      </div>

      <div className="card overflow-hidden">
        {isLoading ? (
          <p className="p-8 text-center text-xs text-[var(--color-ink-faint)]">{t("bmh.loading")}</p>
        ) : !hosts || hosts.length === 0 ? (
          <EmptyState
            icon={Server}
            title={t("bmh.emptyTitle")}
            hint={t("bmh.emptyHint")}
            action={
              <button className="btn btn-primary mt-2" onClick={() => setShowRegister(true)}>
                <Plus size={14} /> {t("bmh.register")}
              </button>
            }
          />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-left text-xs text-[var(--color-ink-muted)]">
                <th className="px-4 py-2.5 font-medium">{t("bmh.colName")}</th>
                <th className="px-4 py-2.5 font-medium">{t("bmh.colPool")}</th>
                <th className="px-4 py-2.5 font-medium">{t("bmh.colBmcAddress")}</th>
                <th className="px-4 py-2.5 font-medium">{t("bmh.colStatus")}</th>
                <th className="px-4 py-2.5 font-medium text-right">{t("bmh.colPower")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {hosts.map((h) => {
                const metadata = h["metadata"] as Record<string, unknown> | undefined;
                const name = String(metadata?.["name"] ?? "");
                const labels = metadata?.["labels"] as Record<string, string> | undefined;
                const spec = h["spec"] as Record<string, unknown> | undefined;
                const bmc = spec?.["bmc"] as Record<string, unknown> | undefined;
                const online = Boolean(spec?.["online"]);
                return (
                  <tr key={name} className="hover:bg-[var(--color-bg)]">
                    <td className="px-4 py-3 font-medium">{name}</td>
                    <td className="px-4 py-3 text-[var(--color-ink-muted)]">
                      {labels?.["node-pool-name"] ?? "—"}
                    </td>
                    <td className="mono px-4 py-3 text-xs text-[var(--color-ink-muted)]">
                      {String(bmc?.["address"] ?? "—")}
                    </td>
                    <td className="px-4 py-3 text-[var(--color-ink-muted)]">{online ? "on" : "off"}</td>
                    <td className="px-4 py-3 text-right">
                      <button
                        className="btn-ghost btn !p-1.5"
                        title={online ? t("bmh.powerOff") : t("bmh.powerOn")}
                        onClick={() => powerMutation.mutate({ name, online: !online })}
                      >
                        {online ? <PowerOff size={14} /> : <Power size={14} />}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {showRegister && <RegisterHostModal onClose={() => setShowRegister(false)} />}
    </div>
  );
}

function RegisterHostModal({ onClose }: { onClose: () => void }) {
  const { t } = useLanguage();
  const qc = useQueryClient();
  const [form, setForm] = useState<BareMetalHostCreate>({
    name: "",
    node_pool_name: "pool1",
    bmc_address: "",
    boot_mac_address: "",
    credentials: { username: "", password: "" },
    online: false,
    disable_certificate_verification: true,
  });
  const [error, setError] = useState<string | null>(null);

  const registerMutation = useMutation({
    mutationFn: () => api.baremetalHosts.register(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["baremetal-hosts"] });
      qc.invalidateQueries({ queryKey: ["hardware-assets"] });
      onClose();
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <Modal title={t("bmh.modalTitle")} onClose={onClose} width={560}>
      <form
        className="flex flex-col gap-3.5"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          registerMutation.mutate();
        }}
      >
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">{t("bmh.hostName")}</label>
            <input
              className="input"
              required
              placeholder="worker-node-01"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </div>
          <div>
            <label className="label">{t("bmh.nodePool")}</label>
            <input
              className="input"
              required
              value={form.node_pool_name}
              onChange={(e) => setForm({ ...form, node_pool_name: e.target.value })}
            />
          </div>
        </div>
        <div>
          <label className="label">{t("bmh.bmcAddress")}</label>
          <input
            className="input mono"
            required
            placeholder="redfish://192.168.1.10/redfish/v1/Systems/1"
            value={form.bmc_address}
            onChange={(e) => setForm({ ...form, bmc_address: e.target.value })}
          />
        </div>
        <div>
          <label className="label">{t("bmh.bootMac")}</label>
          <input
            className="input mono"
            required
            placeholder="aa:bb:cc:dd:ee:ff"
            pattern="^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$"
            value={form.boot_mac_address}
            onChange={(e) => setForm({ ...form, boot_mac_address: e.target.value })}
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">{t("bmh.bmcUsername")}</label>
            <input
              className="input"
              required
              value={form.credentials.username}
              onChange={(e) => setForm({ ...form, credentials: { ...form.credentials, username: e.target.value } })}
            />
          </div>
          <div>
            <label className="label">{t("bmh.bmcPassword")}</label>
            <input
              className="input"
              required
              type="password"
              value={form.credentials.password}
              onChange={(e) => setForm({ ...form, credentials: { ...form.credentials, password: e.target.value } })}
            />
          </div>
        </div>
        <p className="text-[11px] text-[var(--color-ink-faint)]">{t("bmh.passwordHint")}</p>

        {error && <p className="text-xs text-[var(--color-danger)]">{error}</p>}

        <div className="mt-1 flex justify-end gap-2">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            {t("bmh.cancel")}
          </button>
          <button type="submit" className="btn btn-primary" disabled={registerMutation.isPending}>
            {registerMutation.isPending ? t("bmh.submitting") : t("bmh.submit")}
          </button>
        </div>
      </form>
    </Modal>
  );
}
