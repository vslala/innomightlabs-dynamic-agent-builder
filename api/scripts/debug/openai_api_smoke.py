"""Live smoke test for the OpenAI API-key provider.

Lists the models the key offers through ModelsService, then runs a real tool round trip
through OpenAIAPIProvider: the model calls a tool, gets its result, and answers. The key
is read from OPEN_AI_SERVICE_ACCOUNT_KEY and never printed.

    source ../.envrc && PYTHONPATH=. uv run python scripts/debug/openai_api_smoke.py [model]
"""

import asyncio
import json
import os
import sys

from src.crypto import encrypt
from src.llm.models import models_service
from src.llm.providers.openai_api import OpenAIAPIProvider
from src.settings.models import ProviderSettings

WEATHER_TOOL = {
    "type": "function",
    "name": "get_weather",
    "description": "Current weather for a city.",
    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
}


async def turn(provider: OpenAIAPIProvider, messages: list[dict], api_key: str, model: str) -> list:
    events = []
    async for event in provider.stream_response(messages, {"api_key": api_key}, tools=[WEATHER_TOOL], model=model):
        events.append(event)
        if event.type == "text":
            print(event.content, end="", flush=True)
    print()
    return events


async def main() -> None:
    api_key = os.environ.get("OPEN_AI_SERVICE_ACCOUNT_KEY")
    if not api_key:
        sys.exit("OPEN_AI_SERVICE_ACCOUNT_KEY is not set (source ../.envrc)")

    settings = ProviderSettings(
        user_email="smoke@example.com",
        provider_name="OpenAIAPI",
        encrypted_credentials=encrypt(json.dumps({"api_key": api_key})),
    )
    models = models_service.get_openai_api_models(settings)
    print(f"{len(models)} chat models:", ", ".join(model.model_name for model in models))

    model = sys.argv[1] if len(sys.argv) > 1 else "gpt-5.4-mini"
    provider = OpenAIAPIProvider()
    messages: list[dict] = [
        {"role": "system", "content": "You are terse. Use tools when they help."},
        {"role": "user", "content": "What's the weather in Paris?"},
    ]

    print(f"\n[{model}] turn 1")
    events = await turn(provider, messages, api_key, model)
    calls = [event for event in events if event.type == "tool_use"]
    if not calls:
        sys.exit("FAIL: the model did not call get_weather")
    call = calls[0]
    print(f"tool call: {call.tool_name}({call.tool_input})")

    messages += [
        {"role": "assistant", "content": [{"toolUse": {"toolUseId": call.tool_use_id, "name": call.tool_name, "input": call.tool_input}}]},
        {"role": "user", "content": [{"toolResult": {"toolUseId": call.tool_use_id, "content": [{"text": '{"temp_c": 18, "sky": "clear"}'}]}}]},
    ]
    print(f"\n[{model}] turn 2")
    events = await turn(provider, messages, api_key, model)
    usage = next(event for event in events if event.type == "usage")
    stop = next(event for event in events if event.type == "stop")
    print(f"usage: {usage.prompt_tokens} in / {usage.completion_tokens} out, stop: {stop.content}")
    print("OK")


if __name__ == "__main__":
    asyncio.run(main())
