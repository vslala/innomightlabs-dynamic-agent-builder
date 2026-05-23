from __future__ import annotations

from pydantic import BaseModel


class ConnectorDefinition(BaseModel):
    connector_id: str
    provider_name: str
    display_name: str
    connect_path: str
    icon: str


class ConnectorStatus(BaseModel):
    connector_id: str
    provider_name: str
    display_name: str
    connected: bool
    connect_path: str
    icon: str
