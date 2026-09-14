from __future__ import annotations

from pydantic import BaseModel


class AddonCatalogItem(BaseModel):
    name: str
    display_name: str
    category: str
    description: str
    icon: str
    enabled: bool = False  # populated relative to a specific cluster when applicable
    # Real install status (see tasks/addon_tasks.py), not just the
    # "should this be on" intent `enabled` above reflects. None when
    # never installed against this cluster. Kept separate from
    # `enabled` deliberately: an addon can be "enabled" (turned on as an
    # intent) while its actual install is still "installing" or has
    # gone "failed" -- collapsing these into one boolean would hide
    # exactly the information a user clicking "enable" most needs to
    # see next.
    install_status: str | None = None
    install_message: str | None = None


class AddonToggleResult(BaseModel):
    cluster_id: str
    name: str
    enabled: bool
    # Whether enabling this addon actually triggered a real install
    # against a live cluster (True) versus only recording intent because
    # the cluster has no deployed target yet to install anything onto
    # (False, install_status stays None) -- lets the frontend show an
    # accurate "installing..." state instead of assuming one.
    install_triggered: bool = False
