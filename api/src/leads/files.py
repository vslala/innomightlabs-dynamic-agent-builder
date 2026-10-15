"""Files people upload into lead forms (a photo of the damage, a receipt, a brief).

An upload is stored first, pending, under its conversation, and the form submission carries its id. The capture
that uses it claims it once and copies it under the capture, where it lives as long as the capture does. The bytes
are never read by an agent, and a member only ever downloads them as an attachment.
"""

from __future__ import annotations

import os
import re
import time
from datetime import timedelta

from src.agents.image_generation.storage import ConversationMediaStorage
from src.config import settings
from src.form_models import FormInput, FormInputType, FormInputValidation
from src.leads.errors import LeadsError
from src.leads.models import (
    FILE_ACCEPT,
    FILE_EXTENSIONS,
    FILE_MAX_BYTES,
    FILE_MAX_BYTES_CEILING,
    FILE_PENDING_HOURS,
    Answers,
    Capture,
    CaptureFile,
    LeadFile,
    LeadFileKey,
    LeadForm,
    capture_files_prefix,
    sniff_file_type,
)
from src.leads.repository import LeadsRepository
from src.rate_limits.policy import RateLimitPolicy
from src.rate_limits.slots import Limit

PENDING_TAG = "retention=pending-upload"
#: What an upload route reads at most: one byte past the largest file any form allows, so it's refused, not buffered
MAX_UPLOAD_READ = FILE_MAX_BYTES_CEILING + 1
UPLOADS_LIMITED = {"code": "lead_file_upload_limited", "message": "Too many uploads. Try again in a moment."}
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def widget_upload_limits(*, visitor_id: str, key_id: str) -> list[Limit]:
    """The visitor's own uploads, then every upload through the widget key. Fails closed: storage costs the owner."""
    return [
        (
            RateLimitPolicy.sliding_window(
                "WIDGET_LEAD_FILE_UPLOADS", limit=settings.widget_lead_file_uploads_per_visitor_hour, seconds=3600,
                fail_open=False,
            ),
            visitor_id,
        ),
        (
            RateLimitPolicy.fixed_window(
                "WIDGET_LEAD_FILE_UPLOADS_KEY_DAILY", limit=settings.widget_lead_file_uploads_per_key_day,
                seconds=86400, fail_open=False,
            ),
            key_id,
        ),
    ]


class LeadFiles:
    def __init__(self, repository: LeadsRepository | None = None, storage: ConversationMediaStorage | None = None):
        self.repository = repository or LeadsRepository()
        self._storage = storage

    @property
    def storage(self) -> ConversationMediaStorage:
        if self._storage is None:
            self._storage = ConversationMediaStorage()
        return self._storage

    def store(
        self,
        form: LeadForm,
        *,
        input_name: str,
        agent_id: str,
        conversation_id: str,
        uploaded_by: str,
        filename: str,
        raw: bytes,
    ) -> LeadFile:
        """Check the upload against the form's own file input, then keep it pending until a capture claims it."""
        file_input = _file_input(form, input_name)
        validation = file_input.validation or FormInputValidation()
        max_file_bytes = validation.max_file_bytes or FILE_MAX_BYTES
        accept = validation.accept or FILE_ACCEPT
        if len(raw) > max_file_bytes:
            megabytes = max_file_bytes // (1024 * 1024)
            raise LeadsError("FILE_TOO_LARGE", f"{file_input.label}: files can be at most {megabytes} MB.", 413)
        content_type = sniff_file_type(raw)
        if content_type is None or content_type not in accept:
            accepted = ", ".join(FILE_EXTENSIONS[accepted].upper() for accepted in accept)
            raise LeadsError("FILE_TYPE", f"{file_input.label}: upload a {accepted} file.", 415)

        lead_file = LeadFile(
            account_id=form.account_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            form_slug=form.slug,
            input_name=input_name,
            uploaded_by=uploaded_by,
            filename=_display_name(filename, FILE_EXTENSIONS[content_type]),
            content_type=content_type,
            size_bytes=len(raw),
        )
        # The bytes first: a ledger row without bytes would pass the claim and fail every download
        self.storage.put_image(key=lead_file.pending_key, body=raw, content_type=content_type, tagging=PENDING_TAG)
        expires_at = lead_file.created_at + timedelta(hours=FILE_PENDING_HOURS)
        return self.repository.save_lead_file(lead_file, expires_at=int(expires_at.timestamp()))

    def claim(
        self, form: LeadForm, answers: Answers, *, conversation_id: str | None, uploaded_by: str, capture_id: str
    ) -> list[CaptureFile]:
        """The uploads a capture's answers name, moved under the capture. Each must be this person's, for this field."""
        files: list[CaptureFile] = []
        for file_input in form.form_inputs:
            if file_input.input_type != FormInputType.FILE_UPLOAD:
                continue
            for file_id in answers.get(file_input.name, []):
                key = LeadFileKey(conversation_id=conversation_id or "", file_id=file_id, uploaded_by=uploaded_by,
                                  form_slug=form.slug, input_name=file_input.name)
                claimed = self.repository.claim_lead_file(key, capture_id=capture_id, now=int(time.time()))
                if claimed is None:
                    raise LeadsError(
                        "FILE_UNAVAILABLE",
                        f"{file_input.label}: that upload isn't available any more. Ask for it to be uploaded again.",
                    )
                lead_file, claimed_now = claimed
                capture_file = lead_file.as_capture_file()
                if claimed_now:
                    self.storage.copy(lead_file.pending_key, capture_file.storage_key(form.account_id, capture_id))
                    self.storage.delete(lead_file.pending_key)
                files.append(capture_file)
        return files

    def download_url(self, capture: Capture, file_id: str) -> str:
        capture_file = next((file for file in capture.files if file.file_id == file_id), None)
        if capture_file is None:
            raise LeadsError("FILE_NOT_FOUND", "File not found.", 404)
        return self.storage.presign_download_url(
            capture_file.storage_key(capture.account_id, capture.capture_id),
            filename=capture_file.filename,
            content_type=capture_file.content_type,
        )

    def delete_for(self, capture: Capture) -> None:
        if capture.files:
            self.storage.delete_prefix(capture_files_prefix(capture.account_id, capture.capture_id))


def _file_input(form: LeadForm, input_name: str) -> FormInput:
    file_input = next((form_input for form_input in form.form_inputs if form_input.name == input_name), None)
    if file_input is None or file_input.input_type != FormInputType.FILE_UPLOAD:
        raise LeadsError("NOT_A_FILE_FIELD", f"'{input_name}' is not a file field on the form '{form.slug}'.")
    return file_input


def _display_name(filename: str, extension: str) -> str:
    """A name safe to show and to put in a header, with the extension of what the file really is."""
    stem = _UNSAFE_FILENAME_CHARS.sub("-", os.path.splitext(os.path.basename(filename))[0]).strip("-.")[:80]
    return f"{stem or 'upload'}.{extension}"
