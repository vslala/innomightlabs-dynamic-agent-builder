from __future__ import annotations

from typing import Any
from urllib.parse import urlencode, urlparse

from pydantic import ValidationError

from src.config import settings
from src.skills.agent2agent_client.client import A2AHttpClient
from src.skills.agent2agent_client.credentials import A2ACredentialResolver
from src.skills.agent2agent_client.discovery import A2ADiscoveryClient
from src.skills.agent2agent_client.models import (
    A2AAuthResult,
    A2AAgentCardView,
    A2ARegistryConfig,
    DiscoverAgentsRequest,
    GetAgentCardRequest,
    SendMessageRequest,
    SendMessageResponse,
)
from src.skills.agent2agent_client.oauth import (
    A2ARemoteOAuthRepository,
    A2ARemoteOAuthError,
    authorization_code_provider_from_card,
    build_authorization_url,
    create_state_session,
    encode_state_session,
    ensure_valid_access_token,
    generate_code_challenge,
    has_authorization_code_flow,
)
from src.skills.agent2agent_client.references import decode_agent_ref
from src.settings.agent2agent_policy import Agent2AgentPolicy, Agent2AgentPolicyError


async def discover_agents(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    registry_config = _registry_config(config)
    _validate_allowed_urls(context, registry_config.registry_urls)
    request = _validate(DiscoverAgentsRequest, arguments, "discover_agents")
    response = await A2ADiscoveryClient().search(request=request, config=registry_config)
    return response.model_dump(mode="json", exclude_none=True)


async def get_agent_card(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del config
    request = _validate(GetAgentCardRequest, arguments, "get_agent_card")
    agent_ref = decode_agent_ref(request.agent_ref)
    _validate_allowed_urls(context, _agent_ref_urls(agent_ref))
    card = await A2ADiscoveryClient().get_card(agent_ref)
    return card.model_dump(mode="json", exclude_none=True)


async def send_message(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    registry_config = _registry_config(config)
    request = _validate(SendMessageRequest, arguments, "send_message")
    agent_ref = decode_agent_ref(request.agent_ref)
    _validate_allowed_urls(context, _agent_ref_urls(agent_ref))
    http_client = A2AHttpClient()
    credential_resolver = A2ACredentialResolver()
    if not agent_ref.card_url:
        raise ValueError("Discovered A2A agent is missing an Agent Card URL; run discovery again.")
    raw_card = await http_client.get_agent_card(
        agent_ref.card_url,
        headers=credential_resolver.headers_for_url(
            target_url=agent_ref.card_url,
            config=registry_config,
        ),
    )
    card = A2AAgentCardView.model_validate(raw_card)
    preferred_protocols = _preferred_protocols()
    service_url = card.service_url(preferred_protocols) or agent_ref.service_url
    _validate_allowed_urls(context, [service_url])
    direct_headers = credential_resolver.headers_for_url(target_url=service_url, config=registry_config)
    if direct_headers and credential_resolver.supports_bearer_or_api_key(raw_card):
        oauth_result: dict[str, str] | dict[str, Any] | None = direct_headers
    else:
        oauth_result = await _remote_oauth_headers_or_response(
            raw_card=raw_card,
            service_url=service_url,
            registry_config=registry_config,
            context=context,
            agent_name=agent_ref.name,
        )
    if isinstance(oauth_result, dict) and "ok" in oauth_result:
        return oauth_result

    credential = None
    if not oauth_result:
        credential = await credential_resolver.resolve(
            card=raw_card,
            target_url=service_url,
            config=registry_config,
            http_client=http_client,
        )

    if credential and credential.result != A2AAuthResult.READY:
        credential_setup_url = _credential_setup_url(
            context=context,
            service_url=service_url,
        )
        return SendMessageResponse(
            ok=False,
            auth_required=True,
            unsupported_auth=credential.result == A2AAuthResult.UNSUPPORTED,
            message=_credential_message(credential.message, credential_setup_url),
            credential_setup_url=credential_setup_url,
            credential_setup_label="Add Agent2Agent credential" if credential_setup_url else None,
            service_url=service_url,
            agent_name=agent_ref.name,
        ).model_dump(mode="json", exclude_none=True)

    payload = await http_client.send_message(
        agent_card=raw_card,
        request=request,
        headers=oauth_result if isinstance(oauth_result, dict) else credential.headers,
        preferred_protocols=preferred_protocols,
    )
    task = payload.get("task") if isinstance(payload.get("task"), dict) else None
    message = payload.get("message") if isinstance(payload.get("message"), dict) else None
    return SendMessageResponse(
        ok=bool(payload.get("ok")),
        status_code=int(payload.get("status_code", 0) or 0),
        task=task,
        response_text=_extract_response_text(task, request.max_response_chars)
        or _extract_message_text(message, request.max_response_chars),
        message=None if payload.get("ok") else _error_preview(payload),
        service_url=service_url,
        agent_name=agent_ref.name,
    ).model_dump(mode="json", exclude_none=True)


async def resume_message(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del arguments, config, context
    return {
        "ok": False,
        "message": "Credential resume is planned for the OAuth phase and is not available in this release.",
    }


def _registry_config(config: dict[str, Any]) -> A2ARegistryConfig:
    return A2ARegistryConfig.from_runtime_config(config)


def _validate_allowed_urls(context: dict[str, Any], urls: list[str]) -> None:
    owner_email = str(context.get("owner_email") or "").strip()
    if not owner_email:
        raise ValueError("Agent2Agent calls require an owning user context for allowlist validation")
    try:
        Agent2AgentPolicy().validate_urls_for_user(user_email=owner_email, urls=urls)
    except Agent2AgentPolicyError as exc:
        raise ValueError(str(exc)) from exc


def _agent_ref_urls(agent_ref) -> list[str]:
    return [
        url
        for url in [agent_ref.registry_url, agent_ref.card_url, agent_ref.service_url]
        if url
    ]


def _preferred_protocols() -> list[str]:
    supported = [
        protocol
        for protocol in settings.a2a_supported_protocols
        if protocol in {"JSONRPC", "HTTP+JSON"}
    ]
    primary = settings.a2a_primary_protocol
    if primary in supported:
        return [primary, *[protocol for protocol in supported if protocol != primary]]
    return supported or ["JSONRPC"]


def _credential_setup_url(*, context: dict[str, Any], service_url: str) -> str | None:
    agent_id = str(context.get("agent_id") or "").strip()
    installed_skill_id = str(context.get("installed_skill_id") or "").strip()
    if not agent_id or not installed_skill_id:
        return None

    query = urlencode(
        {
            "configure_skill": installed_skill_id,
            "focus": "default_credentials",
            "credential_origin": _origin(service_url),
        }
    )
    return f"{settings.frontend_url.rstrip('/')}/dashboard/agents/{agent_id}/skills?{query}"


async def _remote_oauth_headers_or_response(
    *,
    raw_card: dict[str, Any],
    service_url: str,
    registry_config: A2ARegistryConfig,
    context: dict[str, Any],
    agent_name: str,
) -> dict[str, str] | dict[str, Any] | None:
    if not has_authorization_code_flow(raw_card):
        return None

    owner_email = str(context.get("owner_email") or "").strip()
    agent_id = str(context.get("agent_id") or "").strip()
    installed_skill_id = str(context.get("installed_skill_id") or "").strip()
    if not owner_email or not agent_id or not installed_skill_id:
        return None

    repository = A2ARemoteOAuthRepository()
    target_origin = _origin(service_url)
    record = repository.find(
        owner_email=owner_email,
        installed_skill_id=installed_skill_id,
        target_origin=target_origin,
    )
    if record:
        try:
            credentials = await ensure_valid_access_token(record=record, repository=repository)
            return {"Authorization": f"{_normalize_token_type(credentials.token_type)} {credentials.access_token}"}
        except A2ARemoteOAuthError as exc:
            return _auth_required_response(
                message=str(exc),
                credential_setup_url=_remote_oauth_authorization_url(
                    raw_card=raw_card,
                    service_url=service_url,
                    registry_config=registry_config,
                    context=context,
                ),
                credential_setup_label="Reconnect Agent2Agent OAuth",
                service_url=service_url,
                agent_name=agent_name,
            )

    authorization_url = _remote_oauth_authorization_url(
        raw_card=raw_card,
        service_url=service_url,
        registry_config=registry_config,
        context=context,
    )
    if not authorization_url:
        return _auth_required_response(
            message=(
                "This remote agent requires OAuth 2.0 authorization. Add OAuth client "
                "configuration to this skill installation's Default Registry Credentials."
            ),
            credential_setup_url=_credential_setup_url(context=context, service_url=service_url),
            credential_setup_label="Add Agent2Agent OAuth client",
            service_url=service_url,
            agent_name=agent_name,
        )
    return _auth_required_response(
        message="This remote agent requires OAuth 2.0 authorization. Open this link to grant permission.",
        credential_setup_url=authorization_url,
        credential_setup_label="Connect Agent2Agent OAuth",
        service_url=service_url,
        agent_name=agent_name,
    )


def _remote_oauth_authorization_url(
    *,
    raw_card: dict[str, Any],
    service_url: str,
    registry_config: A2ARegistryConfig,
    context: dict[str, Any],
) -> str | None:
    try:
        provider = authorization_code_provider_from_card(
            card=raw_card,
            target_url=service_url,
            config=registry_config,
        )
    except A2ARemoteOAuthError:
        return None
    if not provider:
        return None

    return_to = str(context.get("return_to") or "")
    if not return_to:
        agent_id = str(context.get("agent_id") or "").strip()
        return_to = f"{settings.frontend_url.rstrip('/')}/dashboard/agents/{agent_id}/skills"
    session = create_state_session(
        user_email=str(context.get("owner_email") or ""),
        agent_id=str(context.get("agent_id") or ""),
        installed_skill_id=str(context.get("installed_skill_id") or ""),
        service_url=service_url,
        return_to=return_to,
        provider=provider,
    )
    return build_authorization_url(
        provider=provider,
        state=encode_state_session(session),
        code_challenge=generate_code_challenge(session.code_verifier),
    )


def _auth_required_response(
    *,
    message: str,
    credential_setup_url: str | None,
    credential_setup_label: str,
    service_url: str,
    agent_name: str,
) -> dict[str, Any]:
    return SendMessageResponse(
        ok=False,
        auth_required=True,
        unsupported_auth=False,
        message=_credential_message(message, credential_setup_url),
        credential_setup_url=credential_setup_url,
        credential_setup_label=credential_setup_label if credential_setup_url else None,
        service_url=service_url,
        agent_name=agent_name,
    ).model_dump(mode="json", exclude_none=True)


def _normalize_token_type(token_type: str) -> str:
    return "Bearer" if token_type.strip().lower() == "bearer" else token_type.strip()


def _credential_message(message: str | None, credential_setup_url: str | None) -> str | None:
    if not message:
        return None
    if not credential_setup_url:
        return message
    return f"{message} Open this link to add the credential: {credential_setup_url}"


def _origin(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}"


def _validate(model_type: type, arguments: dict[str, Any], action_name: str):
    try:
        return model_type.model_validate(arguments)
    except ValidationError as exc:
        raise ValueError(f"Invalid Agent2Agent {action_name} arguments: {exc}") from exc


def _extract_response_text(task: dict[str, Any] | None, max_chars: int) -> str | None:
    if not task:
        return None
    status = task.get("status")
    if not isinstance(status, dict):
        return None
    message = status.get("message")
    if not isinstance(message, dict):
        return None
    return _extract_message_text(message, max_chars)


def _extract_message_text(message: dict[str, Any] | None, max_chars: int) -> str | None:
    if not message:
        return None
    parts = message.get("parts")
    if not isinstance(parts, list):
        return None
    text = "\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict) and part.get("text"))
    return text[:max_chars] if text else None


def _error_preview(payload: dict[str, Any]) -> str:
    for key in ("message", "detail", "body_preview"):
        value = payload.get(key)
        if value:
            return str(value)[:1000]
    return "Remote A2A message request failed"
