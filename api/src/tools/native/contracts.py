"""Input contracts for native agent tools."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CoreMemoryReadInput(BaseModel):
    block: str


class CoreMemoryAppendInput(BaseModel):
    block: str
    content: str


class CoreMemoryReplaceInput(BaseModel):
    block: str
    line_number: int
    new_content: str


class CoreMemoryDeleteInput(BaseModel):
    block: str
    line_number: int


class CoreMemoryListBlocksInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArchivalMemoryInsertInput(BaseModel):
    content: str


class ArchivalMemorySearchInput(BaseModel):
    query: str
    page: int = 1


class RecallConversationInput(BaseModel):
    page: int = 1


class KnowledgeBaseSearchInput(BaseModel):
    query: str
    top_k: int = Field(default=3, ge=1)


class WaitInput(BaseModel):
    seconds: int = Field(default=20, ge=1, le=600)
    reason: str | None = None
