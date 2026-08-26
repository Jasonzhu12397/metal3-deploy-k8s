"""
Explicitly imports every model so `Base.metadata` always has the full set
registered before `init_db()`'s `create_all()` runs -- regardless of
whether some API router happens to import a given model too.

This isn't cosmetic: `models.machine.Machine` was defined but never
imported by any router/service (api/machines.py only proxies to the
Kubernetes API, never touches the local table), so its table silently
never got created. Harmless today because nothing queries it yet, but
exactly the kind of thing that turns into a confusing "no such table"
error the day someone wires up local Machine persistence. Import order
should never be load-bearing for schema completeness.
"""
from app.models.baremetalhost import BareMetalHost
from app.models.cluster import Cluster
from app.models.deployment import Deployment
from app.models.hardware_asset import HardwareAsset
from app.models.machine import Machine
from app.models.pool_assignment import NodePoolAssignment
from app.models.user import User

__all__ = [
    "BareMetalHost",
    "Cluster",
    "Deployment",
    "HardwareAsset",
    "Machine",
    "NodePoolAssignment",
    "User",
]
