from pydantic import BaseModel, Field


class InvokeAgentRequest(BaseModel):
    agent_id: str = Field(min_length=1)
    prompt_template: str = Field(min_length=1)
