from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from src.skills.agent2agent_client.models import A2AAuthResult, A2ARegistryConfig


@dataclass(frozen=True)
class ResolvedCredential:
    result: A2AAuthResult
    headers: dict[str, str]
    message: str | None = None


class A2ACredentialResolver:
    def resolve(self, *, card: dict[str, Any], target_url: str, config: A2ARegistryConfig) -> ResolvedCredential:
        security = card.get("securityRequirements") or card.get("security")
        if not security:
            return ResolvedCredential(result=A2AAuthResult.READY, headers={})

        credential = self._find_credential(target_url=target_url, config=config)
        if credential:
            return ResolvedCredential(
                result=A2AAuthResult.READY,
                headers=self._headers_for_credential(credential),
            )

        if self._supports_bearer_or_api_key(card):
            return ResolvedCredential(
                result=A2AAuthResult.REQUIRED,
                headers={},
                message="This remote agent requires an API key. Add it to this skill installation's Default Registry Credentials.",
            )

        return ResolvedCredential(
            result=A2AAuthResult.UNSUPPORTED,
            headers={},
            message="This remote agent requires an authentication flow that is not supported in this phase.",
        )

    def _find_credential(self, *, target_url: str, config: A2ARegistryConfig) -> str:
        candidates = [target_url.rstrip("/"), _origin(target_url)]
        for registry_url in config.registry_urls:
            candidates.extend([registry_url.rstrip("/"), _origin(registry_url)])

        for candidate in dict.fromkeys(item for item in candidates if item):
            credential = config.default_credentials.get(candidate)
            if credential:
                return credential
        return ""

    def _headers_for_credential(self, credential: str) -> dict[str, str]:
        value = credential.strip()
        if value.lower().startswith(("bearer ", "basic ")):
            return {"Authorization": value}
        return {"Authorization": f"Bearer {value}"}

    def _supports_bearer_or_api_key(self, card: dict[str, Any]) -> bool:
        schemes = card.get("securitySchemes")
        if not isinstance(schemes, dict):
            return False
        return any(
            isinstance(scheme, dict)
            and (
                scheme.get("type") == "apiKey"
                or isinstance(scheme.get("apiKeySecurityScheme"), dict)
                or self._is_bearer_http_auth(scheme)
            )
            for scheme in schemes.values()
        )

    def _is_bearer_http_auth(self, scheme: dict[str, Any]) -> bool:
        http_auth = scheme.get("httpAuthSecurityScheme")
        if not isinstance(http_auth, dict):
            return False
        return str(http_auth.get("scheme") or "").lower() == "bearer"


def _origin(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"
