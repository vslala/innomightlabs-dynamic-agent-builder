"""Reading documents in the background, in this process: after the response when a request submitted the document,
or as a task on the running loop (a tool call, the reaper). The lease on the row makes a second launch harmless."""

import asyncio
import logging
from typing import Optional

from fastapi import BackgroundTasks

from src.documents.models import Document, DocumentOwner

log = logging.getLogger(__name__)

_running: set[asyncio.Task[None]] = set()


def launch(document: Document, background_tasks: Optional[BackgroundTasks] = None) -> None:
    if background_tasks is not None:
        background_tasks.add_task(run, document.owner, document.document_id)
        return
    task = asyncio.get_running_loop().create_task(run(document.owner, document.document_id))
    _running.add(task)
    task.add_done_callback(_running.discard)


async def run(owner: DocumentOwner, document_id: str) -> None:
    from src.documents.service import get_document_service

    try:
        await get_document_service().process(owner, document_id)
    except Exception:
        log.exception("Background processing of document %s failed", document_id)


async def requeue_stale() -> int:
    """The scheduler's reaper (`scheduler/runtime.py`): the scan runs in a thread, so it doesn't hold up the loop (or
    the other reapers due with it); the documents it finds are launched here, on the loop."""
    from src.documents.service import get_document_service

    due: list[Document] = []
    failed = await asyncio.to_thread(get_document_service().requeue_stale, due.append)
    for document in due:
        launch(document)
    return failed
