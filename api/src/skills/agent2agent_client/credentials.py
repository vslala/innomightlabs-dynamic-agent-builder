from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from src.skills.agent2agent_client.models import A2AAuthResult, A2ARegistryConfig


@dataclass(frozen=True)
class ResolvedCredential:
    result: A2AAuthResult
    headers: dict[str, str]
    message: str | None = None


@dataclass(frozen=True)
class OAuth2ClientCredentialsFlow:
    scheme_name: str
    token_url: str
    scopes: list[str]


@dataclass(frozen=True)
class ParsedOAuth2ClientCredentials:
    client_id: str
    client_secret: str


class A2ACredentialResolver:
    async def resolve(
        self,
        *,
        card: dict[str, Any],
        target_url: str,
        config: A2ARegistryConfig,
        http_client: Any | None = None,
    ) -> ResolvedCredential:
        security = card.get("securityRequirements") or card.get("security")
        if not security:
            return ResolvedCredential(result=A2AAuthResult.READY, headers={})

        credential = self._find_credential(target_url=target_url, config=config)
        if credential:
            oauth_flow = self._client_credentials_flow(card)
            oauth_credentials = self._parse_oauth2_client_credentials(credential)
            if oauth_flow and oauth_credentials:
                if not self._token_url_allowed(oauth_flow.token_url, target_url=target_url, config=config):
                    return ResolvedCredential(
                        result=A2AAuthResult.UNSUPPORTED,
                        headers={},
                        message=(
                            "This remote agent's OAuth token endpoint is outside "
                            "the configured A2A registry origins."
                        ),
                    )
                if http_client is None:
                    from src.skills.agent2agent_client.client import A2AHttpClient

                    http_client = A2AHttpClient()
                try:
                    token = await http_client.request_oauth_client_credentials_token(
                        token_url=oauth_flow.token_url,
                        client_id=oauth_credentials.client_id,
                        client_secret=oauth_credentials.client_secret,
                        scopes=oauth_flow.scopes,
                    )
                except Exception as exc:
                    return ResolvedCredential(
                        result=A2AAuthResult.REQUIRED,
                        headers={},
                        message=f"OAuth token exchange failed for this remote agent: {str(exc)[:300]}",
                    )
                access_token = str(token.get("access_token") or "").strip()
                token_type = str(token.get("token_type") or "Bearer").strip()
                if not access_token or token_type.lower() != "bearer":
                    return ResolvedCredential(
                        result=A2AAuthResult.REQUIRED,
                        headers={},
                        message="OAuth token endpoint did not return a Bearer access token.",
                    )
                return ResolvedCredential(
                    result=A2AAuthResult.READY,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            return ResolvedCredential(
                result=A2AAuthResult.READY,
                headers=self._headers_for_credential(credential),
            )

        if self._client_credentials_flow(card):
            return ResolvedCredential(
                result=A2AAuthResult.REQUIRED,
                headers={},
                message=(
                    "This remote agent requires OAuth 2.0 client credentials. "
                    "Add client_id:client_secret to this skill installation's Default Registry Credentials."
                ),
            )

        if self._supports_bearer_or_api_key(card):
            return ResolvedCredential(
                result=A2AAuthResult.REQUIRED,
                headers={},
                message=(
                    "This remote agent requires an API key. Add it to this "
                    "skill installation's Default Registry Credentials."
                ),
            )

        return ResolvedCredential(
            result=A2AAuthResult.UNSUPPORTED,
            headers={},
            message="This remote agent requires an authentication flow that is not supported in this phase.",
        )

    def headers_for_url(self, *, target_url: str, config: A2ARegistryConfig) -> dict[str, str]:
        credential = self._find_credential(target_url=target_url, config=config)
        if not credential:
            return {}
        if self._parse_oauth2_client_credentials(credential):
            return {}
        return self._headers_for_credential(credential)

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
        return self.supports_bearer_or_api_key(card)

    def supports_bearer_or_api_key(self, card: dict[str, Any]) -> bool:
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

    def _client_credentials_flow(self, card: dict[str, Any]) -> OAuth2ClientCredentialsFlow | None:
        schemes = card.get("securitySchemes")
        if not isinstance(schemes, dict):
            return None
        requirements = _security_requirements(card)
        for scheme_name, scheme in schemes.items():
            if not isinstance(scheme, dict):
                continue
            flow = _extract_client_credentials_flow(scheme)
            if not flow:
                continue
            required_scopes = _required_scopes_for_scheme(requirements, str(scheme_name))
            scopes = required_scopes or list(flow.get("scopes", {}).keys())
            token_url = str(flow.get("tokenUrl") or flow.get("token_url") or "").strip()
            if token_url:
                return OAuth2ClientCredentialsFlow(
                    scheme_name=str(scheme_name),
                    token_url=token_url,
                    scopes=scopes,
                )
        return None

    def _parse_oauth2_client_credentials(self, credential: str) -> ParsedOAuth2ClientCredentials | None:
        value = credential.strip()
        if not value or value.lower().startswith(("bearer ", "basic ")):
            return None
        if value.startswith("{"):
            try:
                payload = json.loads(value)
            except json.JSONDecodeError:
                return None
            if not isinstance(payload, dict):
                return None
            client_id = str(payload.get("client_id") or payload.get("clientId") or "").strip()
            client_secret = str(payload.get("client_secret") or payload.get("clientSecret") or "").strip()
            if client_id and client_secret:
                return ParsedOAuth2ClientCredentials(client_id=client_id, client_secret=client_secret)
            return None
        client_id, separator, client_secret = value.partition(":")
        if not separator:
            return None
        client_id = client_id.strip()
        client_secret = client_secret.strip()
        if not client_id or not client_secret:
            return None
        return ParsedOAuth2ClientCredentials(client_id=client_id, client_secret=client_secret)

    def _token_url_allowed(self, token_url: str, *, target_url: str, config: A2ARegistryConfig) -> bool:
        token_origin = _origin(token_url)
        if not token_origin:
            return False
        allowed_origins = {_origin(target_url)}
        allowed_origins.update(_origin(registry_url) for registry_url in config.registry_urls)
        return token_origin in allowed_origins


def _origin(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _extract_client_credentials_flow(scheme: dict[str, Any]) -> dict[str, Any] | None:
    oauth2 = scheme.get("oauth2SecurityScheme") if isinstance(scheme.get("oauth2SecurityScheme"), dict) else scheme
    if not isinstance(oauth2, dict):
        return None
    if oauth2.get("type") not in {None, "oauth2"} and "flows" not in oauth2:
        return None
    flows = oauth2.get("flows")
    if not isinstance(flows, dict):
        return None
    flow = flows.get("clientCredentials") or flows.get("client_credentials")
    return flow if isinstance(flow, dict) else None


def _security_requirements(card: dict[str, Any]) -> list[dict[str, list[str]]]:
    raw_requirements = card.get("securityRequirements") or card.get("security") or []
    requirements: list[dict[str, list[str]]] = []
    if not isinstance(raw_requirements, list):
        return requirements
    for raw_requirement in raw_requirements:
        if not isinstance(raw_requirement, dict):
            continue
        schemes = (
            raw_requirement.get("schemes")
            if isinstance(raw_requirement.get("schemes"), dict)
            else raw_requirement
        )
        if not isinstance(schemes, dict):
            continue
        requirement: dict[str, list[str]] = {}
        for scheme_name, raw_scopes in schemes.items():
            requirement[str(scheme_name)] = _scope_list(raw_scopes)
        requirements.append(requirement)
    return requirements


def _required_scopes_for_scheme(requirements: list[dict[str, list[str]]], scheme_name: str) -> list[str]:
    for requirement in requirements:
        if scheme_name in requirement:
            return requirement[scheme_name]
    return []


def _scope_list(raw_scopes: Any) -> list[str]:
    if isinstance(raw_scopes, list):
        return [str(scope).strip() for scope in raw_scopes if str(scope).strip()]
    if isinstance(raw_scopes, dict):
        values = raw_scopes.get("list")
        if isinstance(values, list):
            return [str(scope).strip() for scope in values if str(scope).strip()]
    return []
