from __future__ import annotations

from pydantic import BaseModel


class BMCPowerAction(BaseModel):
    action: str  # "on" | "off" | "reboot"


class BMCPowerStatus(BaseModel):
    host: str
    power_state: str
