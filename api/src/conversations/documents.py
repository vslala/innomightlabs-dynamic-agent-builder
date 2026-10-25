"""A conversation's documents as message references: attached when a message is sent, shown to the agent as
`<attached_document>`, and swept when uploaded and never sent. Registered with `messages.references` on import.

A conversation's documents are the conversation's, whoever uploaded them (docs/LLD-documents.md, section 3.6).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.documents.models import Document, DocumentNotFound, DocumentOwner, DocumentStatus, OwnerKind
from src.documents.service import get_document_service
from src.messages.models import MessageReference
from src.messages.references import ReferenceRefused, register

if TYPE_CHECKING:
    from src.conversations.models import Conversation

KIND = "document"
#: An upload never sent with a message is removed after this long.
UNSENT_TTL_SECONDS = 24 * 60 * 60

READ_HINT = "Read it with describe_document, then the section, page or table tools; don't guess what it says."


def document_owner(conversation: "Conversation") -> DocumentOwner:
    return DocumentOwner(account_id=conversation.account_id, kind=OwnerKind.CONVERSATION, owner_id=conversation.conversation_id)


def document_tag(document: Document) -> str:
    """How an attached document reads in the conversation: enough to pick the next call, never its content."""
    attributes = f'id="{document.document_id}" filename="{document.filename}" status="{document.status.value}"'
    if document.status == DocumentStatus.READY:
        attributes += f' pages="{document.page_count}" tables="{document.table_count}"'
        note = READ_HINT
    elif document.status == DocumentStatus.FAILED:
        note = f"It couldn't be read: {document.error}"
    else:
        note = "It is still being read; list_documents shows when it is ready."
    return f"<attached_document {attributes}>\n{note}\n</attached_document>"


class ConversationDocuments:
    kind = KIND

    def attach(self, conversation: "Conversation", ids: list[str]) -> list[MessageReference]:
        try:
            documents = get_document_service().attach(document_owner(conversation), ids)
        except DocumentNotFound as exc:
            raise ReferenceRefused("reference_not_found", "An attached document wasn't found. Please attach it again.") from exc
        return [MessageReference(kind=KIND, id=document.document_id, label=document.filename) for document in documents]

    def describe(self, conversation: "Conversation", references: list[MessageReference]) -> dict[str, str]:
        current = {document.document_id: document for document in get_document_service().documents(document_owner(conversation))}
        return {reference.id: document_tag(current[reference.id]) for reference in references if reference.id in current}

    def recall_line(self, reference: MessageReference) -> str:
        return f"[document {reference.id} {reference.label}]"


def sweep_unsent() -> int:
    """The scheduler's sweep: conversation uploads never sent with a message."""
    return get_document_service().sweep_unsent(OwnerKind.CONVERSATION, older_than_seconds=UNSENT_TTL_SECONDS)


register(ConversationDocuments())
