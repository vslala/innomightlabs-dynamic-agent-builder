import pytest
from google.protobuf.json_format import ParseError

from tools.a2a_agent_card_validator import (
    AgentCardValidationError,
    validate_agent_card_payload,
)


def _valid_agent_card_payload() -> dict:
    return {
        "name": "InnomightLabs A2A Facilitator",
        "description": "Discovery entrypoint for public A2A agents.",
        "supportedInterfaces": [
            {
                "protocolBinding": "JSONRPC",
                "protocolVersion": "1.0",
                "url": "http://localhost:1455/a2a",
            }
        ],
        "version": "1.0.0",
        "capabilities": {
            "streaming": True,
            "pushNotifications": False,
            "extendedAgentCard": False,
        },
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": [
            {
                "id": "discover_public_agents",
                "name": "Discover Public Agents",
                "description": "List agents enabled for A2A communication.",
                "tags": ["discovery"],
            }
        ],
    }


def test_validate_agent_card_payload_accepts_a2a_v1_shape():
    card = validate_agent_card_payload(_valid_agent_card_payload())

    assert card.name == "InnomightLabs A2A Facilitator"
    assert card.supported_interfaces[0].protocol_binding == "JSONRPC"


def test_validate_agent_card_payload_rejects_unknown_legacy_fields():
    payload = {
        **_valid_agent_card_payload(),
        "protocolVersion": "1.0.0",
    }

    with pytest.raises(ParseError, match="protocolVersion"):
        validate_agent_card_payload(payload)


def test_validate_agent_card_payload_rejects_missing_supported_interfaces():
    payload = _valid_agent_card_payload()
    del payload["supportedInterfaces"]

    with pytest.raises(AgentCardValidationError, match="supportedInterfaces"):
        validate_agent_card_payload(payload)
