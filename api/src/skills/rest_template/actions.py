from __future__ import annotations

import time
from typing import Any, cast

import httpx
from pydantic import ValidationError

from src.common import outbound
from src.skills.rest_template.helper import (
    AgentSecrets,
    body_preview,
    compact_response,
    content_type,
    full_response,
    normalize_string_map,
    parse_body_json,
    redact_url,
    transport_error_response,
)
from src.skills.rest_template.models import RestPostRequest, RestRequest


async def get(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del context
    secrets = _secrets(config)
    return cast(dict[str, Any], secrets.scrub(await _send_request("GET", _validate(RestRequest, "GET", arguments, secrets), secrets)))


async def post(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del context
    secrets = _secrets(config)
    return cast(dict[str, Any], secrets.scrub(await _send_request("POST", _validate(RestPostRequest, "POST", arguments, secrets), secrets)))


def _secrets(config: dict[str, Any]) -> AgentSecrets:
    return AgentSecrets(normalize_string_map(config.get("secrets"), "secrets"))


def _validate(
    model: type[RestRequest], method: str, arguments: dict[str, Any], secrets: AgentSecrets
) -> RestRequest:
    try:
        return model.model_validate(secrets.expand(arguments))
    except ValidationError as exc:
        raise ValueError(secrets.scrub(f"Invalid REST Template {method} arguments: {exc}")) from exc


async def _send_request(method: str, request: RestRequest, secrets: AgentSecrets) -> dict[str, Any]:
    started = time.perf_counter()
    origin = httpx.URL(request.url).copy_with(path="/", query=None, fragment=None)

    async def drop_secret_headers_across_origins(outgoing: httpx.Request) -> None:
        # httpx strips only Authorization when a redirect leaves the origin.
        if outgoing.url.copy_with(path="/", query=None, fragment=None) == origin:
            return
        for name in [name for name, value in outgoing.headers.items() if secrets.carried_by(value)]:
            del outgoing.headers[name]

    try:
        async with outbound.async_client(
            timeout=request.timeout_seconds,
            event_hooks={"request": [drop_secret_headers_across_origins]},
        ) as client:
            response = await client.request(method, request.url, **_request_kwargs(request))
    except httpx.TimeoutException:
        return transport_error_response(
            f"REST {method} timed out after {request.timeout_seconds} seconds while calling {redact_url(request.url)}"
        )
    except httpx.RequestError as exc:
        return transport_error_response(f"REST {method} could not connect to {redact_url(request.url)}: {exc}")

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    preview, truncated = body_preview(response.text, request.max_response_chars)
    if not request.include_full_response:
        return compact_response(response, preview)

    response_content_type = content_type(response.headers)
    return full_response(
        method=method,
        response=response,
        preview=preview,
        body_json=parse_body_json(response, response_content_type),
        truncated=truncated,
        elapsed_ms=elapsed_ms,
    )


def _request_kwargs(request: RestRequest) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "params": request.query,
        "headers": request.headers,
    }
    if isinstance(request, RestPostRequest):
        kwargs.update(_body_kwargs(request))
    return kwargs


def _body_kwargs(request: RestPostRequest) -> dict[str, Any]:
    if request.json_body is not None:
        return {"json": request.json_body}
    if request.text_body is not None:
        return {"content": request.text_body}
    return {}
