"""The one shape every blueprint problem takes, from YAML errors to plan blockers."""

from typing import Optional

from pydantic import BaseModel


class BlueprintIssue(BaseModel):
    #: Dotted path into the document, e.g. `resources.widget.agent` or `resources.assistant.skills[0].id`.
    path: str
    message: str
    #: How to fix it, when there's something specific to say ("Did you mean 'assistant'?").
    hint: Optional[str] = None
    line: Optional[int] = None


class BlueprintInvalid(Exception):
    def __init__(self, issues: list[BlueprintIssue]):
        self.issues = issues
        super().__init__("; ".join(issue.message for issue in issues))
