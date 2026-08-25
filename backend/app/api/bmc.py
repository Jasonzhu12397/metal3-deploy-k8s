from __future__ import annotations

from fastapi import APIRouter

from app.services.metal3 import Metal3Service

router = APIRouter(prefix="/bmc", tags=["bmc"])
metal3_service = Metal3Service()


@router.post("/{host_name}/power/{action}")
async def bmc_power_action(host_name: str, action: str):
    """action: on | off | reboot. Power state is driven through the
    BareMetalHost object (spec.online) so Metal3's baremetal-operator stays
    the single source of truth for actual BMC calls."""
    if action == "reboot":
        metal3_service.set_power_state(host_name, False)
        metal3_service.set_power_state(host_name, True)
    else:
        metal3_service.set_power_state(host_name, action == "on")
    return {"host": host_name, "action": action}
