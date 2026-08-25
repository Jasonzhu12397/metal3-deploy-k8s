from __future__ import annotations

from pydantic import BaseModel


class AddonCatalogItem(BaseModel):
    name: str
    display_name: str
    category: str
    description: str
    icon: str
    enabled: bool = False  # populated relative to a specific cluster when applicable


class AddonToggleResult(BaseModel):
    cluster_id: str
    name: str
    enabled: bool
