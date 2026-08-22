import os

import httpx
import pytest
from google.protobuf.json_format import ParseError

from tools.a2a_agent_card_validator import (
    AgentCardValidationError,
    validate_agent_card_url,
)


RUN_CONTRACT_TEST_ENV = "RUN_A2A_AGENT_CARD_CONTRACT_TEST"
AGENT_CARD_URL_ENV = "A2A_AGENT_CARD_URL"


@pytest.mark.integration
def test_agent_card_matches_official_a2a_v1_proto_schema():
    if os.getenv(RUN_CONTRACT_TEST_ENV) != "1":
        pytest.skip(
            f"Set {RUN_CONTRACT_TEST_ENV}=1 to validate a running A2A endpoint."
        )

    agent_card_url = os.getenv(AGENT_CARD_URL_ENV)
    if not agent_card_url:
        pytest.fail(
            f"Set {AGENT_CARD_URL_ENV} to an agent-specific card URL such as "
            "http://localhost:1455/a2a/agents/{agent_id}/card.",
            pytrace=False,
        )

    error_message = None
    try:
        validate_agent_card_url(agent_card_url)
    except (AgentCardValidationError, ParseError, httpx.HTTPError, ValueError) as error:
        error_message = str(error)

    if error_message:
        pytest.fail(
            f"Invalid A2A Agent Card at {agent_card_url}: {error_message}",
            pytrace=False,
        )
