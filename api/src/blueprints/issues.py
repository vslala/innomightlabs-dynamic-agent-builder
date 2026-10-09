"""The one shape every blueprint problem takes, from YAML errors to plan blockers."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class IssueOwner(str, Enum):
    """Who fixes it."""

    #: Whoever writes the blueprint: Ada, or a person writing YAML.
    AUTHOR = "author"
    #: The person it's built for: a setting only they know, which the builder asks them for in a form.
    PERSON = "person"


class BlueprintIssue(BaseModel):
    #: Dotted path into the document, e.g. `resources.widget.agent` or `resources.assistant.skills[0].id`.
    path: str
    message: str
    #: How to fix it, when there's something specific to say ("Did you mean 'assistant'?").
    hint: Optional[str] = None
    line: Optional[int] = None
    owner: IssueOwner = IssueOwner.AUTHOR


class BlueprintInvalid(Exception):
    def __init__(self, issues: list[BlueprintIssue]):
        self.issues = issues
        super().__init__("; ".join(issue.message for issue in issues))
