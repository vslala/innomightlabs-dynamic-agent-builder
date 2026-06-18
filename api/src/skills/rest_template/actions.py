from __future__ import annotations

import time
from typing import Any

import httpx
from pydantic import ValidationError

from src.skills.rest_template.helper import (
    body_preview,
    compact_response,
    content_type,
    expand_env_placeholders,
    full_response,
    parse_body_json,
    redact_url,
    transport_error_response,
)
from src.skills.rest_template.models import RestPostRequest, RestRequest


async def get(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del config, context
    return await _send_request("GET", _validate_get(arguments))


async def post(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del config, context
    return await _send_request("POST", _validate_post(arguments))


def _validate_get(arguments: dict[str, Any]) -> RestRequest:
    try:
        return RestRequest.model_validate(expand_env_placeholders(arguments))
    except ValidationError as exc:
        raise ValueError(f"Invalid REST Template GET arguments: {exc}") from exc


def _validate_post(arguments: dict[str, Any]) -> RestPostRequest:
    try:
        return RestPostRequest.model_validate(expand_env_placeholders(arguments))
    except ValidationError as exc:
        raise ValueError(f"Invalid REST Template POST arguments: {exc}") from exc


async def _send_request(method: str, request: RestRequest | RestPostRequest) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=request.timeout_seconds, follow_redirects=True) as client:
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


def _request_kwargs(request: RestRequest | RestPostRequest) -> dict[str, Any]:
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
