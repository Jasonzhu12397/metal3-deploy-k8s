from __future__ import annotations

import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.cluster import Cluster, InfrastructureProvider
from app.models.hardware_asset import AssetStatus, HardwareAsset
from app.models.pool_assignment import NodePoolAssignment
from app.schemas.pool_assignment import ClusterManifestBundle, PoolAssignmentRead, PoolAssignRequest
from app.services.asset_planner import AssetPlannerService
from app.services.cloud_planner import CloudPlannerService
from app.services.cpu_topology import compute_reserved_cpus, isolated_cpu_count

router = APIRouter(prefix="/clusters/{cluster_id}", tags=["planner"])
planner = AssetPlannerService()
cloud_planner = CloudPlannerService()


async def _get_cluster(cluster_id: uuid.UUID, db: AsyncSession) -> Cluster:
    cluster = await db.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(404, "Cluster not found")
    return cluster


@router.post("/pools/{pool_name}/assign", response_model=list[PoolAssignmentRead], status_code=201)
async def assign_assets_to_pool(
    cluster_id: uuid.UUID,
    pool_name: str,
    payload: PoolAssignRequest,
    db: AsyncSession = Depends(get_db),
):
    """The core 'pick hardware in the UI' action: bind a set of
    HardwareAssets into a named pool on this cluster, with the operator's
    CPU-reservation / hugepage choices. Rejects assets that are already
    reserved elsewhere. Metal3-only -- cloud/VM providers (OpenStack/
    vSphere/KubeVirt) declare their machine pools directly at cluster
    creation time (flavor/image, no physical hardware to pick)."""
    cluster = await _get_cluster(cluster_id, db)
    if cluster.infrastructure_provider != InfrastructureProvider.METAL3:
        raise HTTPException(
            409,
            f"Cluster uses infrastructure_provider={cluster.infrastructure_provider.value} -- "
            "there's no physical hardware to assign for a cloud/VM provider. Its worker pools "
            "(flavor/image/count) are set on the cluster itself; see PATCH /clusters/{id}.",
        )

    assets = []
    for asset_id in payload.asset_ids:
        asset = await db.get(HardwareAsset, asset_id)
        if not asset:
            raise HTTPException(404, f"Asset {asset_id} not found")
        if asset.status not in (AssetStatus.AVAILABLE, AssetStatus.DISCOVERED):
            raise HTTPException(409, f"Asset '{asset.name}' is not available (status={asset.status})")
        assets.append(asset)

    created = []
    for asset in assets:
        assignment = NodePoolAssignment(
            cluster_id=cluster.id,
            pool_name=pool_name,
            asset_id=asset.id,
            role=payload.role,
            reserved_cores_per_socket=payload.reserved_cores_per_socket,
            cpu_manager_policy=payload.cpu_manager_policy,
            topology_manager_policy=payload.topology_manager_policy,
            isolation_interrupts=payload.isolation_interrupts,
            hugepage_type=payload.hugepage_type,
            hugepage_count_1gb=payload.hugepage_count_1gb,
            hugepage_count_2mb=payload.hugepage_count_2mb,
            nic_role_overrides=payload.nic_role_overrides,
            disk_role_overrides=payload.disk_role_overrides,
        )
        asset.status = AssetStatus.RESERVED
        asset.cluster_id = cluster.id
        asset.node_pool_name = pool_name
        db.add(assignment)
        created.append((assignment, asset))

    await db.commit()

    out = []
    for assignment, asset in created:
        await db.refresh(assignment)
        reserved = compute_reserved_cpus(
            asset.cpu_sockets, asset.cpu_cores_per_socket, assignment.reserved_cores_per_socket,
            asset.cpu_threads_per_core,
        )
        isolated = isolated_cpu_count(
            asset.cpu_sockets, asset.cpu_cores_per_socket, asset.cpu_threads_per_core,
            assignment.reserved_cores_per_socket,
        )
        item = PoolAssignmentRead.model_validate(assignment)
        item.computed_reserved_cpus = reserved
        item.computed_isolated_cpu_count = isolated
        out.append(item)
    return out


@router.delete("/pools/{pool_name}/assets/{asset_id}", status_code=204)
async def unassign_asset(
    cluster_id: uuid.UUID, pool_name: str, asset_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    result = await db.scalars(
        select(NodePoolAssignment).where(
            NodePoolAssignment.cluster_id == cluster_id,
            NodePoolAssignment.pool_name == pool_name,
            NodePoolAssignment.asset_id == asset_id,
        )
    )
    assignment = result.first()
    if not assignment:
        raise HTTPException(404, "Assignment not found")
    asset = await db.get(HardwareAsset, asset_id)
    if asset:
        asset.status = AssetStatus.AVAILABLE
        asset.cluster_id = None
        asset.node_pool_name = None
    await db.delete(assignment)
    await db.commit()


@router.get("/pools", response_model=dict[str, list[PoolAssignmentRead]])
async def list_pools(cluster_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.scalars(
        select(NodePoolAssignment).where(NodePoolAssignment.cluster_id == cluster_id)
    )
    by_pool: dict[str, list[PoolAssignmentRead]] = defaultdict(list)
    for assignment in result.all():
        asset = await db.get(HardwareAsset, assignment.asset_id)
        item = PoolAssignmentRead.model_validate(assignment)
        if asset:
            item.computed_reserved_cpus = compute_reserved_cpus(
                asset.cpu_sockets, asset.cpu_cores_per_socket,
                assignment.reserved_cores_per_socket, asset.cpu_threads_per_core,
            )
            item.computed_isolated_cpu_count = isolated_cpu_count(
                asset.cpu_sockets, asset.cpu_cores_per_socket, asset.cpu_threads_per_core,
                assignment.reserved_cores_per_socket,
            )
        by_pool[assignment.pool_name].append(item)
    return by_pool


@router.post("/manifests/generate", response_model=ClusterManifestBundle)
async def generate_manifests(cluster_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Renders this cluster's Cluster API manifests -- for metal3, that
    means bmh.yaml / cluster-config.yaml / per-node network policies
    straight from whatever hardware has been assigned to its pools
    (nothing hand-typed); for a cloud/VM provider (OpenStack/vSphere/
    KubeVirt) there's no hardware to assign, so it's just the
    cluster-config.yaml rendered from the flavor/image/count set at
    cluster-creation time."""
    cluster = await _get_cluster(cluster_id, db)

    if cluster.infrastructure_provider != InfrastructureProvider.METAL3:
        try:
            cluster_config_yaml = cloud_planner.generate_cluster_config_yaml(cluster)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return ClusterManifestBundle(
            bmh_yaml="",
            cluster_config_yaml=cluster_config_yaml,
            network_policies={},
            eph_net_yaml=None,
        )

    result = await db.scalars(
        select(NodePoolAssignment).where(NodePoolAssignment.cluster_id == cluster_id)
    )
    assignments = result.all()
    if not assignments:
        raise HTTPException(409, "No hardware assigned to any pool yet -- call /pools/{pool}/assign first")

    pools: dict[str, tuple[list[HardwareAsset], list[NodePoolAssignment]]] = {}
    for assignment in assignments:
        asset = await db.get(HardwareAsset, assignment.asset_id)
        if not asset:
            continue
        pools.setdefault(assignment.pool_name, ([], []))
        pools[assignment.pool_name][0].append(asset)
        pools[assignment.pool_name][1].append(assignment)

    cluster_spec = {
        "name": cluster.name,
        "namespace": cluster.namespace,
        "control_plane_count": cluster.control_plane_count,
        "control_plane_endpoint": cluster.control_plane_endpoint,
        **cluster.spec,
    }

    try:
        bundle = planner.generate_bundle(cluster_spec, pools)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    return ClusterManifestBundle(
        bmh_yaml=bundle["bmh_yaml"],
        cluster_config_yaml=bundle["cluster_config_yaml"],
        network_policies=bundle["network_policies"],
        eph_net_yaml=bundle.get("eph_net_yaml"),
    )
