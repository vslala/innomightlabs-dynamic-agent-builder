"""Secret key authentication for the public /v1 API."""

import logging
from dataclasses import dataclass
from typing import Annotated, Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.public_api.keys import SECRET_KEY_PREFIX, AgentSecretKey, SecretKeyRepository, hash_secret
from src.users import UserRepository
from src.users.models import UserStatus

log = logging.getLogger(__name__)

bearer = HTTPBearer(auto_error=False, description="An agent secret key: sk_live_…")


@dataclass(frozen=True)
class PublicApiCaller:
    """A verified secret key and the agent it belongs to. The key acts as the agent's owner."""

    key: AgentSecretKey
    agent: Agent

    @property
    def owner_email(self) -> str:
        return self.key.created_by


def require_secret_key(
    agent_id: str,
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer)],
) -> PublicApiCaller:
    if not credentials or not credentials.credentials.startswith(SECRET_KEY_PREFIX):
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Send 'Authorization: Bearer sk_live_…'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    repo = SecretKeyRepository()
    key = repo.find_by_hash(hash_secret(credentials.credentials))
    if not key or not key.is_active:
        raise HTTPException(status_code=401, detail="Invalid API key", headers={"WWW-Authenticate": "Bearer"})
    if key.agent_id != agent_id:
        raise HTTPException(status_code=403, detail="This API key is not valid for this agent")

    owner = UserRepository().get_by_email(key.created_by)
    if not owner or owner.status in (UserStatus.INACTIVE.value, UserStatus.PENDING_DELETION.value):
        raise HTTPException(status_code=401, detail="Invalid API key", headers={"WWW-Authenticate": "Bearer"})

    agent = AgentRepository().find_agent_by_id(key.agent_id, key.created_by)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        repo.record_request(key.agent_id, key.key_id)
    except Exception:
        log.exception("Failed to record request for secret key %s", key.key_id)

    return PublicApiCaller(key=key, agent=agent)
