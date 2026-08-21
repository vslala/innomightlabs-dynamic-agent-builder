from __future__ import annotations

import sys
from typing import Any

import httpx
from a2a.types import AgentCard
from google.protobuf.json_format import ParseDict, ParseError


REQUIRED_AGENT_CARD_FIELDS = {
    "name",
    "description",
    "supportedInterfaces",
    "version",
    "capabilities",
    "defaultInputModes",
    "defaultOutputModes",
    "skills",
}


class AgentCardValidationError(ValueError):
    pass


def validate_agent_card_payload(payload: dict[str, Any]) -> AgentCard:
    missing_fields = REQUIRED_AGENT_CARD_FIELDS - payload.keys()
    if missing_fields:
        raise AgentCardValidationError(
            f"Missing required fields: {', '.join(sorted(missing_fields))}"
        )

    card = ParseDict(
        payload,
        AgentCard(),
        ignore_unknown_fields=False,
    )

    if not card.supported_interfaces:
        raise AgentCardValidationError("supportedInterfaces must not be empty")
    if not card.default_input_modes:
        raise AgentCardValidationError("defaultInputModes must not be empty")
    if not card.default_output_modes:
        raise AgentCardValidationError("defaultOutputModes must not be empty")
    if not card.skills:
        raise AgentCardValidationError("skills must not be empty")

    return card


def fetch_agent_card_payload(url: str) -> dict[str, Any]:
    response = httpx.get(url, timeout=15)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise AgentCardValidationError("Agent Card response must be a JSON object")
    return payload


def validate_agent_card_url(url: str) -> AgentCard:
    return validate_agent_card_payload(fetch_agent_card_payload(url))


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python -m tools.a2a_agent_card_validator <agent-card-url>", file=sys.stderr)
        return 2

    url = sys.argv[1]
    try:
        validate_agent_card_url(url)
    except (AgentCardValidationError, ParseError, httpx.HTTPError, ValueError) as error:
        print(f"Invalid Agent Card: {error}", file=sys.stderr)
        return 1

    print(f"Valid A2A v1.0 Agent Card: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
