from __future__ import annotations

import json
import logging
from typing import Optional

import httpx

from src.connectors.models import ConnectorDefinition, ConnectorStatus
from src.crypto import decrypt
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
    "google_ads": ConnectorDefinition(
        connector_id="google_ads",
        provider_name="GoogleAds",
        display_name="Google Ads",
        connect_path="/auth/google-ads/start",
        icon="megaphone",
    ),
}

PROVIDER_TO_CONNECTOR_ID = {
    definition.provider_name: definition.connector_id for definition in CONNECTORS.values()
}

GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

log = logging.getLogger(__name__)


class ConnectorService:
    """The account's connector status, backed by its ProviderSettings records."""

    def __init__(
        self,
        provider_settings_repository: Optional[ProviderSettingsRepository] = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.provider_settings_repository = provider_settings_repository or get_provider_settings_repository()
        self._transport = transport

    async def disconnect(self, account_id: str, connector_id: str) -> None:
        """End the connection: revoke the grant at Google, then forget the credentials. Revoking is best effort, so a
        token Google already rejects (or an outage) never leaves the connector impossible to remove. Raises ValueError
        when there is nothing to disconnect."""
        definition = self.get_definition(connector_id)
        stored = (
            self.provider_settings_repository.find_by_provider(account_id, definition.provider_name) if definition else None
        )
        if definition is None or stored is None:
            raise ValueError("Connector not found")
        await self._revoke_google_grant(definition, stored.encrypted_credentials)
        if not self.provider_settings_repository.delete(account_id, definition.provider_name):
            raise RuntimeError(f"Could not disconnect {definition.display_name}")
        log.info("Disconnected %s for account %s", connector_id, account_id)

    async def _revoke_google_grant(self, definition: ConnectorDefinition, encrypted_credentials: str) -> None:
        try:
            credentials = json.loads(decrypt(encrypted_credentials))
            # The refresh token ends the whole grant; the access token alone would leave it alive
            token = credentials.get("refresh_token") or credentials.get("access_token")
            if not token:
                return
            async with httpx.AsyncClient(transport=self._transport, timeout=10.0) as client:
                response = await client.post(GOOGLE_REVOKE_URL, data={"token": token})
            if not response.is_success:
                log.warning("Google did not revoke the %s grant (%s)", definition.connector_id, response.status_code)
        except Exception as error:  # never include the error text: it could carry the token
            log.warning("Revoking the %s grant failed: %s", definition.connector_id, type(error).__name__)

    def get_definition(self, connector_id: str) -> ConnectorDefinition | None:
        return CONNECTORS.get(connector_id)

    def list_statuses(self, account_id: str) -> list[ConnectorStatus]:
        return [
            ConnectorStatus(
                connector_id=definition.connector_id,
                provider_name=definition.provider_name,
                display_name=definition.display_name,
                connected=self.is_connected(account_id, definition.connector_id),
                connect_path=f"/connectors/{definition.connector_id}/start",
                icon=definition.icon,
            )
            for definition in CONNECTORS.values()
        ]

    def is_connected(self, account_id: str, connector_id: str) -> bool:
        definition = self.get_definition(connector_id)
        if not definition:
            return False
        return self.provider_settings_repository.find_by_provider(
            account_id,
            definition.provider_name,
        ) is not None

    def get_status(self, account_id: str, connector_id: str) -> ConnectorStatus | None:
        definition = self.get_definition(connector_id)
        if not definition:
            return None
        return ConnectorStatus(
            connector_id=definition.connector_id,
            provider_name=definition.provider_name,
            display_name=definition.display_name,
            connected=self.is_connected(account_id, connector_id),
            connect_path=definition.connect_path,
            icon=definition.icon,
        )

    def statuses_for_manifest(
        self,
        manifest: SkillManifest,
        account_id: str | None,
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
                        self.is_connected(account_id, dependency.connector_id)
                        if account_id
                        else False
                    ),
                    connect_path=definition.connect_path if definition else None,
                )
            )
        return statuses

    def missing_required_connectors(
        self,
        manifest: SkillManifest,
        account_id: str,
    ) -> list[str]:
        missing: list[str] = []
        for dependency in manifest.connectors:
            if dependency.required and not self.is_connected(account_id, dependency.connector_id):
                missing.append(dependency.connector_id)
        return missing


def connector_id_for_provider(provider_name: str | None) -> str | None:
    if not provider_name:
        return None
    return PROVIDER_TO_CONNECTOR_ID.get(provider_name)


def get_connector_service() -> ConnectorService:
    return ConnectorService()
