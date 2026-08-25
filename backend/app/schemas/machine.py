from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel

from app.models.machine import MachineRole


class MachineRead(BaseModel):
    id: uuid.UUID
    name: str
    role: MachineRole
    cluster_id: uuid.UUID
    baremetalhost_id: Optional[uuid.UUID] = None
    phase: str

    class Config:
        from_attributes = True
