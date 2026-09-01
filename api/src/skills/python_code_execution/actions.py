from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from src.skills.python_code_execution.client import get_python_runner_client
from src.skills.python_code_execution.models import RunScriptRequest, RunScriptResult


async def run_script(
    arguments: dict[str, Any],
    config: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    del config
    request = _validate_request(arguments)
    response = await get_python_runner_client().run_script(request, context)
    return RunScriptResult.from_runner(response).model_dump(mode="json")


def _validate_request(arguments: dict[str, Any]) -> RunScriptRequest:
    try:
        return RunScriptRequest.model_validate(arguments)
    except ValidationError as exc:
        raise ValueError(f"Invalid Python code execution run_script arguments: {exc}") from exc
