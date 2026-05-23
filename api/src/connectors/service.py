from __future__ import annotations

from typing import Optional

from src.connectors.models import ConnectorDefinition, ConnectorStatus
from src.settings.repository import ProviderSettingsRepository, get_provider_settings_repository
from src.skills.models import SkillConnectorStatus, SkillManifest


CONNECTORS: dict[str, ConnectorDefinition] = {
    "google_drive": ConnectorDefinition(
        connector_id="google_drive",
        provider_name="GoogleDrive",
        display_name="Google Drive",
        connect_path="/auth/google-drive/start",
        icon="hard_drive",
    ),
    "google_mail": ConnectorDefinition(
        connector_id="google_mail",
        provider_name="GoogleMail",
        display_name="Gmail",
        connect_path="/auth/google-mail/start",
        icon="mail",
    ),
}

PROVIDER_TO_CONNECTOR_ID = {
    definition.provider_name: definition.connector_id for definition in CONNECTORS.values()
}


class ConnectorService:
    """User-level connector status backed by existing ProviderSettings records."""

    def __init__(self, provider_settings_repository: Optional[ProviderSettingsRepository] = None):
        self.provider_settings_repository = provider_settings_repository or get_provider_settings_repository()

    def get_definition(self, connector_id: str) -> ConnectorDefinition | None:
        return CONNECTORS.get(connector_id)

    def list_statuses(self, user_email: str) -> list[ConnectorStatus]:
        return [
            ConnectorStatus(
                connector_id=definition.connector_id,
                provider_name=definition.provider_name,
                display_name=definition.display_name,
                connected=self.is_connected(user_email, definition.connector_id),
                connect_path=f"/connectors/{definition.connector_id}/start",
                icon=definition.icon,
            )
            for definition in CONNECTORS.values()
        ]

    def is_connected(self, user_email: str, connector_id: str) -> bool:
        definition = self.get_definition(connector_id)
        if not definition:
            return False
        return self.provider_settings_repository.find_by_provider(
            user_email,
            definition.provider_name,
        ) is not None

    def get_status(self, user_email: str, connector_id: str) -> ConnectorStatus | None:
        definition = self.get_definition(connector_id)
        if not definition:
            return None
        return ConnectorStatus(
            connector_id=definition.connector_id,
            provider_name=definition.provider_name,
            display_name=definition.display_name,
            connected=self.is_connected(user_email, connector_id),
            connect_path=definition.connect_path,
            icon=definition.icon,
        )

    def statuses_for_manifest(
        self,
        manifest: SkillManifest,
        user_email: str | None,
    ) -> list[SkillConnectorStatus]:
        statuses: list[SkillConnectorStatus] = []
        for dependency in manifest.connectors:
            definition = self.get_definition(dependency.connector_id)
            provider_name = definition.provider_name if definition else dependency.connector_id
            statuses.append(
                SkillConnectorStatus(
                    connector_id=dependency.connector_id,
                    provider_name=provider_name,
                    required=dependency.required,
                    connected=(
                        self.is_connected(user_email, dependency.connector_id)
                        if user_email
                        else False
                    ),
                    connect_path=definition.connect_path if definition else None,
                )
            )
        return statuses

    def missing_required_connectors(
        self,
        manifest: SkillManifest,
        user_email: str,
    ) -> list[str]:
        missing: list[str] = []
        for dependency in manifest.connectors:
            if dependency.required and not self.is_connected(user_email, dependency.connector_id):
                missing.append(dependency.connector_id)
        return missing


def connector_id_for_provider(provider_name: str | None) -> str | None:
    if not provider_name:
        return None
    return PROVIDER_TO_CONNECTOR_ID.get(provider_name)


def get_connector_service() -> ConnectorService:
    return ConnectorService()
