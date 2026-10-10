"""Ada, the solution builder: the one agent that runs on the Vishwakarma architecture.

Ada is never stored or listed with the person's agents. She's built here for each turn, on the person's own
provider, and her conversations carry ADA_AGENT_ID so the dashboard chat can find her routes.
"""

from src.agents.architectures.vishwakarma import ARCHITECTURE_NAME, VishwakarmaArchitecture
from src.agents.models import Agent
from src.builder.models import ADA_AGENT_ID, BuilderSession

__all__ = ["ADA_AGENT_ID", "ADA_NAME", "GREETING", "ada_agent", "ada_architecture"]
ADA_NAME = "Ada"
#: Ada's first message, saved when the session starts so the person sees it before typing anything.
GREETING = "Hi, I'm Ada. What do you want to build today?"


def ada_agent(session: BuilderSession) -> Agent:
    return Agent(
        agent_id=ADA_AGENT_ID,
        agent_name=ADA_NAME,
        agent_architecture=ARCHITECTURE_NAME,
        agent_provider=session.provider,
        agent_model=session.model,
        agent_persona="Ada, the InnomightLabs solution builder.",
        # A build can pause for a while (reading a website, the person checking their site); keep the whole thread.
        session_timeout_minutes=0,
        created_by=session.user_email,
    )


def ada_architecture() -> VishwakarmaArchitecture:
    return VishwakarmaArchitecture()
