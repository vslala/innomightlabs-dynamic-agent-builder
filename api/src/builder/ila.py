"""Ila, the solution builder: the one agent that runs on the Vishwakarma architecture.

Ila is never stored or listed with the person's agents. She's built here for each turn, on the person's own
provider, and her conversations carry ILA_AGENT_ID so the dashboard chat can find her routes.
"""

from src.agents.architectures.vishwakarma import ARCHITECTURE_NAME, VishwakarmaArchitecture
from src.agents.models import Agent
from src.builder.models import ILA_AGENT_ID, BuilderSession

__all__ = ["ILA_AGENT_ID", "ILA_NAME", "GREETING", "ila_agent", "ila_architecture"]
ILA_NAME = "Ila"
#: Ila's first message, saved when the session starts so the person sees it before typing anything.
GREETING = "Hi, I'm Ila. What do you want to build today?"


def ila_agent(session: BuilderSession) -> Agent:
    return Agent(
        agent_id=ILA_AGENT_ID,
        agent_name=ILA_NAME,
        agent_architecture=ARCHITECTURE_NAME,
        agent_provider=session.provider,
        agent_model=session.model,
        agent_persona="Ila, the InnomightLabs solution builder.",
        # A build can pause for a while (reading a website, the person checking their site); keep the whole thread.
        session_timeout_minutes=0,
        created_by=session.user_email,
    )


def ila_architecture() -> VishwakarmaArchitecture:
    return VishwakarmaArchitecture()
