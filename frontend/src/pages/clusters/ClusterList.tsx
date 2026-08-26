import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Boxes, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { EmptyState } from "../../components/ui/EmptyState";
import { Modal } from "../../components/ui/Modal";
import { StatusTag } from "../../components/ui/StatusTag";
import type { ClusterCreate } from "../../lib/types";

export default function ClusterList() {
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const { data: clusters, isLoading } = useQuery({ queryKey: ["clusters"], queryFn: api.clusters.list });

  const removeMutation = useMutation({
    mutationFn: (id: string) => api.clusters.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["clusters"] }),
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-[var(--color-ink-muted)]">
          定义要通过 Cluster API + Metal3 部署的目标集群。建好之后去"硬件资产"里把物理机分配进它的节点池。
        </p>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
          <Plus size={14} /> 新建集群
        </button>
      </div>

      <div className="card overflow-hidden">
        {isLoading ? (
          <div className="p-10 text-center text-xs text-[var(--color-ink-faint)]">加载中...</div>
        ) : !clusters || clusters.length === 0 ? (
          <EmptyState
            icon={Boxes}
            title="还没有集群"
            hint="点击右上角「新建集群」，定义名称、控制面数量和网段，然后就可以往它的节点池里分配硬件了。"
            action={
              <button className="btn btn-primary mt-2" onClick={() => setShowCreate(true)}>
                <Plus size={14} /> 新建集群
              </button>
            }
          />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-left text-xs text-[var(--color-ink-muted)]">
                <th className="px-4 py-2.5 font-medium">名称</th>
                <th className="px-4 py-2.5 font-medium">部署目标</th>
                <th className="px-4 py-2.5 font-medium">状态</th>
                <th className="px-4 py-2.5 font-medium">命名空间</th>
                <th className="px-4 py-2.5 font-medium">控制面数量</th>
                <th className="px-4 py-2.5 font-medium">控制面 Endpoint</th>
                <th className="px-4 py-2.5 font-medium text-right">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {clusters.map((c) => (
                <tr key={c.id} className="hover:bg-[var(--color-bg)]">
                  <td className="px-4 py-3">
                    <Link to={`/clusters/${c.id}`} className="font-medium text-[var(--color-brand-600)]">
                      {c.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <span className="rounded-full bg-[var(--color-idle-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-ink-muted)]">
                      {c.infrastructure_provider}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <StatusTag status={c.status} />
                  </td>
                  <td className="px-4 py-3 text-[var(--color-ink-muted)]">{c.namespace}</td>
                  <td className="px-4 py-3 text-[var(--color-ink-muted)]">{c.control_plane_count}</td>
                  <td className="mono px-4 py-3 text-xs text-[var(--color-ink-muted)]">
                    {c.control_plane_endpoint ?? "—"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      className="btn-ghost btn !p-1.5"
                      title="删除"
                      onClick={() => {
                        if (confirm(`确定删除集群 "${c.name}"？这不会撤销已经 apply 到管理集群的资源。`)) {
                          removeMutation.mutate(c.id);
                        }
                      }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showCreate && <CreateClusterModal onClose={() => setShowCreate(false)} />}
    </div>
  );
}

const PROVIDERS: { value: NonNullable<ClusterCreate["infrastructure_provider"]>; label: string; hint: string }[] = [
  { value: "metal3", label: "Metal3（裸金属）", hint: "从硬件资产库存里挑物理机，走 Ironic + baremetal-operator" },
  { value: "openstack", label: "OpenStack（CAPO）", hint: "VM 跑在现有 OpenStack 云上，按 flavor/image 声明" },
  { value: "vsphere", label: "vSphere（CAPV）", hint: "VM 跑在 vCenter 上，按 flavor/image（VM 模板）声明" },
  { value: "kubevirt", label: "KubeVirt（CAPK，通用 KVM）", hint: "VM 作为 KubeVirt VirtualMachine 跑在一个已装 KubeVirt 的管理集群里" },
];

function CreateClusterModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<ClusterCreate>({
    name: "",
    namespace: "metal3",
    infrastructure_provider: "metal3",
    control_plane_count: 3,
    control_plane_endpoint: "",
    spec: { pod_cidr: "192.168.0.0/16", service_cidr: "10.96.0.0/12", k8s_version: "v1.29.0" },
  });
  const [error, setError] = useState<string | null>(null);
  const isCloud = form.infrastructure_provider !== "metal3" && form.infrastructure_provider !== undefined;

  const createMutation = useMutation({
    mutationFn: () => api.clusters.create(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["clusters"] });
      onClose();
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <Modal title="新建集群" onClose={onClose} width={600}>
      <form
        className="flex flex-col gap-3.5"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          createMutation.mutate();
        }}
      >
        <div>
          <label className="label">集群名称</label>
          <input
            className="input"
            required
            placeholder="pk-cnis-pcg"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </div>

        <div>
          <label className="label">部署目标（Cluster API Infrastructure Provider）</label>
          <div className="grid grid-cols-2 gap-2">
            {PROVIDERS.map((p) => (
              <button
                key={p.value}
                type="button"
                onClick={() => setForm({ ...form, infrastructure_provider: p.value })}
                className={`rounded-lg border p-2.5 text-left transition ${
                  form.infrastructure_provider === p.value
                    ? "border-[var(--color-brand-500)] bg-[var(--color-brand-50)]"
                    : "border-[var(--color-border-strong)] hover:border-[var(--color-brand-500)]"
                }`}
              >
                <div className="text-xs font-semibold">{p.label}</div>
                <div className="mt-0.5 text-[10px] text-[var(--color-ink-faint)]">{p.hint}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">命名空间</label>
            <input
              className="input"
              value={form.namespace}
              onChange={(e) => setForm({ ...form, namespace: e.target.value })}
            />
          </div>
          <div>
            <label className="label">控制面节点数</label>
            <input
              className="input"
              type="number"
              min={1}
              value={form.control_plane_count}
              onChange={(e) => setForm({ ...form, control_plane_count: Number(e.target.value) })}
            />
            {!isCloud && (
              <p className="mt-1 text-[10px] text-[var(--color-ink-faint)]">
                Metal3 集群这里只是初始值——实际数量以后面分配的 control-plane 角色硬件数量为准
              </p>
            )}
          </div>
        </div>
        <div>
          <label className="label">控制面 Endpoint（VIP）</label>
          <input
            className="input mono"
            placeholder="10.138.165.27"
            value={form.control_plane_endpoint ?? ""}
            onChange={(e) => setForm({ ...form, control_plane_endpoint: e.target.value })}
          />
        </div>

        {isCloud && (
          <>
            <div className="grid grid-cols-2 gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
              <div>
                <label className="label">控制面 Flavor / 规格</label>
                <input
                  className="input"
                  required
                  placeholder="m1.large"
                  value={form.control_plane_flavor ?? ""}
                  onChange={(e) => setForm({ ...form, control_plane_flavor: e.target.value })}
                />
              </div>
              <div>
                <label className="label">控制面 Image / 模板</label>
                <input
                  className="input"
                  required
                  placeholder="ubuntu-22.04"
                  value={form.control_plane_image ?? ""}
                  onChange={(e) => setForm({ ...form, control_plane_image: e.target.value })}
                />
              </div>
            </div>

            <WorkerPoolEditor
              pools={form.worker_pools ?? []}
              onChange={(pools) => setForm({ ...form, worker_pools: pools })}
            />
          </>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Pod CIDR</label>
            <input
              className="input mono"
              value={(form.spec?.pod_cidr as string) ?? ""}
              onChange={(e) => setForm({ ...form, spec: { ...form.spec, pod_cidr: e.target.value } })}
            />
          </div>
          <div>
            <label className="label">Service CIDR</label>
            <input
              className="input mono"
              value={(form.spec?.service_cidr as string) ?? ""}
              onChange={(e) => setForm({ ...form, spec: { ...form.spec, service_cidr: e.target.value } })}
            />
          </div>
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
    </Modal>
  );
}

function WorkerPoolEditor({
  pools,
  onChange,
}: {
  pools: NonNullable<ClusterCreate["worker_pools"]>;
  onChange: (pools: NonNullable<ClusterCreate["worker_pools"]>) => void;
}) {
  const addPool = () =>
    onChange([...pools, { name: `pool${pools.length + 1}`, count: 1, flavor: "", image: "" }]);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <label className="label !mb-0">Worker 节点池</label>
        <button type="button" className="btn btn-secondary !py-1 !text-[11px]" onClick={addPool}>
          <Plus size={12} /> 加一个池
        </button>
      </div>
      {pools.length === 0 ? (
        <p className="text-[11px] text-[var(--color-ink-faint)]">还没有 worker 池（只有控制面也可以，先建集群，以后再加）</p>
      ) : (
        pools.map((pool, i) => (
          <div key={i} className="grid grid-cols-[1fr_70px_1fr_1fr_28px] gap-1.5">
            <input
              className="input !text-xs"
              placeholder="池名"
              value={pool.name}
              onChange={(e) => {
                const next = [...pools];
                next[i] = { ...pool, name: e.target.value };
                onChange(next);
              }}
            />
            <input
              className="input !text-xs"
              type="number"
              min={1}
              placeholder="数量"
              value={pool.count}
              onChange={(e) => {
                const next = [...pools];
                next[i] = { ...pool, count: Number(e.target.value) };
                onChange(next);
              }}
            />
            <input
              className="input !text-xs"
              placeholder="flavor"
              value={pool.flavor ?? ""}
              onChange={(e) => {
                const next = [...pools];
                next[i] = { ...pool, flavor: e.target.value };
                onChange(next);
              }}
            />
            <input
              className="input !text-xs"
              placeholder="image"
              value={pool.image ?? ""}
              onChange={(e) => {
                const next = [...pools];
                next[i] = { ...pool, image: e.target.value };
                onChange(next);
              }}
            />
            <button
              type="button"
              className="btn-ghost btn !p-1"
              onClick={() => onChange(pools.filter((_, idx) => idx !== i))}
            >
              <Trash2 size={13} />
            </button>
          </div>
        ))
      )}
    </div>
  );
}
