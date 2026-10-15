"""Leads: the forms an account collects with, and the captures its agents make. See docs/LLD-lead-capture.md."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from src.form_models import Form, FormInput, FormInputType, FormInputValidation
from src.skills.models import ActorKind
from src.utils.dynamodb import convert_decimals, convert_floats_to_decimals

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,47}$")
INPUT_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
STATUS_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")

MAX_INPUTS = 30
MAX_OPTIONS = 50
TEXT_MAX_LENGTH = 2000
FILE_MAX_BYTES = 10 * 1024 * 1024
FILE_MAX_BYTES_CEILING = 25 * 1024 * 1024
FILE_MAX_ITEMS_CEILING = 5
#: The types a file input may accept: those we recognise from their first bytes, whatever the name claims
FILE_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/webp": (b"RIFF",),  # with "WEBP" at offset 8, checked in sniff_file_type
    "application/pdf": (b"%PDF-",),
}
FILE_EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "application/pdf": "pdf"}
FILE_ACCEPT = list(FILE_SIGNATURES)
#: An upload nobody captured is deleted after this; the media bucket's lifecycle rule
#: (terraform/conversation_media.tf, tag retention=pending-upload) deletes the bytes after a day
FILE_PENDING_HOURS = 24

#: Lead forms are shown to anonymous visitors, so they use only the parts of the form schema that are safe there
VISITOR_INPUT_TYPES = {
    FormInputType.TEXT,
    FormInputType.TEXT_AREA,
    FormInputType.SELECT,
    FormInputType.CHOICE,
    FormInputType.FILE_UPLOAD,
}
VISITOR_ATTRS = {"optional", "help_text", "variant", "placeholder", "agent_hint"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def visitor_input(form_input: FormInput) -> FormInput:
    """`form_input` as a lead form keeps it: checked against what visitors may see, with the lead defaults filled in."""
    label = f"Field '{form_input.name}'"
    if not INPUT_NAME_RE.fullmatch(form_input.name):
        raise ValueError(f"{label}: names are lower case letters, digits and underscores, starting with a letter")
    if form_input.input_type not in VISITOR_INPUT_TYPES:
        raise ValueError(f"{label}: {form_input.input_type.value} inputs can't be shown to visitors")
    if form_input.options_source or form_input.options_filter or form_input.smart_suggestion:
        raise ValueError(f"{label}: dynamic options and smart suggestions are dashboard-only")
    unknown_attrs = set(form_input.attr or {}) - VISITOR_ATTRS
    if unknown_attrs:
        raise ValueError(f"{label}: unsupported attr {', '.join(sorted(unknown_attrs))}")

    is_choice = form_input.input_type in {FormInputType.SELECT, FormInputType.CHOICE}
    option_count = len(form_input.options or []) + len(form_input.values or [])
    if is_choice and not option_count:
        raise ValueError(f"{label}: list the options a visitor can pick")
    if option_count > MAX_OPTIONS:
        raise ValueError(f"{label}: at most {MAX_OPTIONS} options")

    validation = form_input.validation or FormInputValidation()
    if validation.pattern:
        _require_pattern(label, validation.pattern)
    if form_input.input_type == FormInputType.FILE_UPLOAD:
        validation = _with_file_defaults(label, validation)
    elif not is_choice and validation.max_length is None:
        validation = validation.model_copy(update={"max_length": TEXT_MAX_LENGTH})
    return form_input.model_copy(update={"validation": validation})


def _require_pattern(label: str, pattern: str) -> None:
    if len(pattern) > 200:
        raise ValueError(f"{label}: the pattern is longer than 200 characters")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"{label}: the pattern is not a valid regular expression ({exc})") from None


def _with_file_defaults(label: str, validation: FormInputValidation) -> FormInputValidation:
    max_file_bytes = validation.max_file_bytes or FILE_MAX_BYTES
    max_items = validation.max_items or 1
    if max_file_bytes > FILE_MAX_BYTES_CEILING:
        raise ValueError(f"{label}: files can be at most {FILE_MAX_BYTES_CEILING // (1024 * 1024)} MB")
    if max_items > FILE_MAX_ITEMS_CEILING:
        raise ValueError(f"{label}: at most {FILE_MAX_ITEMS_CEILING} files")
    accept = validation.accept or FILE_ACCEPT
    unknown = set(accept) - set(FILE_SIGNATURES)
    if unknown:
        raise ValueError(f"{label}: files can be {', '.join(FILE_ACCEPT)}, not {', '.join(sorted(unknown))}")
    return validation.model_copy(update={"max_file_bytes": max_file_bytes, "max_items": max_items, "accept": accept})


def sniff_file_type(raw: bytes) -> str | None:
    """The file's type from its first bytes, or None when it isn't one we accept."""
    for content_type, signatures in FILE_SIGNATURES.items():
        if raw.startswith(signatures):
            if content_type == "image/webp" and raw[8:12] != b"WEBP":
                continue
            return content_type
    return None


class LeadFormFields(BaseModel):
    """What a person writes when they define a form; shared by the API requests and the stored form."""

    name: str = Field(min_length=1, max_length=80)
    #: Why the account collects this; the agent reads it to explain itself
    purpose: str | None = Field(default=None, max_length=500)
    form_inputs: list[FormInput] = Field(min_length=1, max_length=MAX_INPUTS)

    @field_validator("form_inputs")
    @classmethod
    def _visitor_inputs(cls, form_inputs: list[FormInput]) -> list[FormInput]:
        names = [form_input.name for form_input in form_inputs]
        duplicates = {name for name in names if names.count(name) > 1}
        if duplicates:
            raise ValueError(f"Field names must be unique: {', '.join(sorted(duplicates))}")
        return [visitor_input(form_input) for form_input in form_inputs]


class LeadForm(LeadFormFields):
    """A form an account's agents fill in. Agents name it by `slug` (`{{ lead_form:<slug> }}`), which never changes."""

    form_id: str = Field(default_factory=lambda: uuid4().hex)
    account_id: str
    slug: str
    version: int = 1
    status: Literal["active", "archived"] = "active"
    #: Kept by the capture transaction; form edits update fields in place so they never overwrite it
    capture_count: int = 0
    created_by: str
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime | None = None

    @field_validator("slug")
    @classmethod
    def _valid_slug(cls, slug: str) -> str:
        if not SLUG_RE.fullmatch(slug):
            raise ValueError("Slugs are 2 to 48 lower case letters, digits and hyphens, starting with a letter or digit")
        return slug

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    def as_form(self, submit_path: str) -> Form:
        return Form(form_name=self.name, submit_path=submit_path, form_inputs=self.form_inputs)

    def revised(self, fields: LeadFormFields) -> LeadForm:
        """This form with new fields; a change to its inputs is a new version, since captures snapshot the inputs."""
        inputs_changed = fields.form_inputs != self.form_inputs
        return self.model_copy(
            update={
                "name": fields.name,
                "purpose": fields.purpose,
                "form_inputs": fields.form_inputs,
                "version": self.version + 1 if inputs_changed else self.version,
                "updated_at": _now(),
            }
        )

    @property
    def pk(self) -> str:
        return f"Account#{self.account_id}"

    @property
    def sk(self) -> str:
        return f"LeadForm#{self.form_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        item: dict[str, Any] = convert_floats_to_decimals({
            **self.model_dump(mode="json"),
            "pk": self.pk,
            "sk": self.sk,
            "entity_type": "LeadForm",
        })
        return item

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> LeadForm:
        return cls.model_validate(convert_decimals(item))


class LeadStatus(BaseModel):
    key: str
    label: str = Field(min_length=1, max_length=40)
    #: Lets reports and the board group any account's own statuses
    stage: Literal["open", "won", "lost"]

    @field_validator("key")
    @classmethod
    def _valid_key(cls, key: str) -> str:
        if not STATUS_KEY_RE.fullmatch(key):
            raise ValueError("Status keys are lower case letters, digits and underscores, starting with a letter")
        return key


DEFAULT_STATUSES = [
    LeadStatus(key="new", label="New", stage="open"),
    LeadStatus(key="contacted", label="Contacted", stage="open"),
    LeadStatus(key="qualified", label="Qualified", stage="open"),
    LeadStatus(key="won", label="Won", stage="won"),
    LeadStatus(key="lost", label="Lost", stage="lost"),
]


class LeadSettings(BaseModel):
    """The account's lead statuses, in order. The first is what new captures get."""

    account_id: str
    statuses: list[LeadStatus] = Field(default_factory=lambda: list(DEFAULT_STATUSES), min_length=1, max_length=20)
    updated_by: str | None = None
    updated_at: datetime | None = None

    @field_validator("statuses")
    @classmethod
    def _unique_keys(cls, statuses: list[LeadStatus]) -> list[LeadStatus]:
        keys = [status.key for status in statuses]
        if len(set(keys)) != len(keys):
            raise ValueError("Status keys must be unique")
        return statuses

    @property
    def initial_status(self) -> str:
        return self.statuses[0].key

    @property
    def status_keys(self) -> set[str]:
        return {status.key for status in self.statuses}

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            **self.model_dump(mode="json"),
            "pk": f"Account#{self.account_id}",
            "sk": "LeadSettings",
            "entity_type": "LeadSettings",
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> LeadSettings:
        return cls.model_validate(convert_decimals(item))


CaptureSource = Literal["widget", "dashboard", "api", "a2a"]

#: Owners and members chatting in the dashboard are testing their agent (automation runs act as the owner too)
SOURCE_BY_ACTOR: dict[ActorKind, CaptureSource] = {
    ActorKind.OWNER: "dashboard",
    ActorKind.MEMBER: "dashboard",
    ActorKind.API: "api",
    ActorKind.A2A: "a2a",
    ActorKind.VISITOR: "widget",
    ActorKind.GUEST: "widget",
}

Answers = dict[str, Any]


def capture_id_for(account_id: str, form_id: str, actor_id: str, answers: Answers) -> str:
    """The same person giving the same answers on the same form is one lead, however many times the agent retries.

    The conversation is left out on purpose: an agent may gather a lead over several visits.
    """
    canonical = json.dumps([account_id, form_id, actor_id, answers], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


class LeadFile(BaseModel):
    """A file a person uploaded into a lead form, waiting for the capture that uses it.

    Key: `CONVERSATION#{conversation_id}` / `LEADFILE#{file_id}`, so it goes with the conversation. A pending row
    carries a `ttl`; claiming it removes the ttl and records the capture.
    """

    file_id: str = Field(default_factory=lambda: uuid4().hex)
    account_id: str
    agent_id: str
    conversation_id: str
    form_slug: str
    input_name: str
    uploaded_by: str
    filename: str
    content_type: str
    size_bytes: int
    claimed_by: str | None = None
    created_at: datetime = Field(default_factory=_now)

    @property
    def extension(self) -> str:
        return FILE_EXTENSIONS[self.content_type]

    @property
    def pending_key(self) -> str:
        """Under the conversation, so deleting the conversation deletes an upload nobody captured."""
        return f"agents/{self.agent_id}/conversations/{self.conversation_id}/lead-files/{self.file_id}.{self.extension}"

    def as_capture_file(self) -> CaptureFile:
        return CaptureFile(
            file_id=self.file_id, input_name=self.input_name, filename=self.filename,
            content_type=self.content_type, size_bytes=self.size_bytes,
        )

    def to_dynamo_item(self, ttl: int) -> dict[str, Any]:
        return {
            **self.model_dump(mode="json", exclude_none=True),
            "pk": f"CONVERSATION#{self.conversation_id}",
            "sk": f"LEADFILE#{self.file_id}",
            "ttl": ttl,
            "entity_type": "LeadFile",
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> LeadFile:
        return cls.model_validate(convert_decimals(item))


class LeadFileKey(BaseModel):
    """Which upload a capture wants, and on whose behalf: everything the claim checks."""

    conversation_id: str
    file_id: str
    uploaded_by: str
    form_slug: str
    input_name: str


class CaptureFile(BaseModel):
    """A file kept with its capture, as long as the capture is."""

    file_id: str
    input_name: str
    filename: str
    content_type: str
    size_bytes: int

    def storage_key(self, account_id: str, capture_id: str) -> str:
        return f"{capture_files_prefix(account_id, capture_id)}{self.file_id}.{FILE_EXTENSIONS[self.content_type]}"


def capture_files_prefix(account_id: str, capture_id: str) -> str:
    """Outside every conversation and agent prefix, so a capture's files outlive the chat they came from."""
    return f"leads/{account_id}/{capture_id}/"


class LabelledAnswer(BaseModel):
    """An answer that carries its own label: what `register_lead` sends, and what leads looked like before forms."""

    field_id: str
    label: str
    value: str


def ad_hoc_form(answers: list[LabelledAnswer]) -> tuple[list[FormInput], Answers]:
    """The inputs and answers of a capture made without a lead form, so it reads like any other capture."""
    inputs = [FormInput(input_type=FormInputType.TEXT, name=answer.field_id, label=answer.label) for answer in answers]
    return inputs, {answer.field_id: answer.value for answer in answers}


class Capture(BaseModel):
    """A completed form: the answers, checked against the form version they were given for."""

    capture_id: str
    account_id: str
    #: None for captures from before lead forms existed (register_lead and the migration)
    form_id: str | None = None
    form_slug: str | None = None
    form_name: str
    form_version: int | None = None
    #: The inputs as they were, so a capture stays readable after its form changes
    form_inputs: list[FormInput]
    answers: Answers
    agent_id: str
    conversation_id: str | None = None
    actor_kind: ActorKind
    actor_id: str
    actor_email: str | None = None
    source: CaptureSource
    status: str
    files: list[CaptureFile] = Field(default_factory=list)
    #: Its place in its month's count, for the plan limit; None for test captures, which are not counted
    month_seq: int | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime | None = None

    @property
    def is_test(self) -> bool:
        return self.source == "dashboard"

    @property
    def month(self) -> str:
        return self.created_at.strftime("%Y-%m")

    def event_payload(self) -> dict[str, Any]:
        """The lead as automations see it (`{{ trigger.lead.* }}`): stable, documented in docs/LLD-lead-capture.md.

        Files are listed without links; a step that needs the bytes can't reach them from here by design.
        """
        return {
            "capture_id": self.capture_id,
            "form_slug": self.form_slug,
            "form_name": self.form_name,
            "form_version": self.form_version,
            "agent_id": self.agent_id,
            "conversation_id": self.conversation_id,
            "source": self.source,
            "status": self.status,
            "answers": self.answers,
            "fields": [{"name": form_input.name, "label": form_input.label} for form_input in self.form_inputs],
            "files": [file.model_dump(mode="json") for file in self.files],
            "created_at": self.created_at.isoformat(),
        }

    def is_locked(self, monthly_limit: int) -> bool:
        """Past the plan's monthly limit: kept, but hidden until the account upgrades. Zero means unlimited."""
        return monthly_limit > 0 and self.month_seq is not None and self.month_seq > monthly_limit

    @property
    def pk(self) -> str:
        return f"Account#{self.account_id}"

    @property
    def sk(self) -> str:
        return f"Capture#{self.created_at.isoformat()}#{self.capture_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        # Absent rather than null, so "not counted" is simply attribute_not_exists(month_seq)
        item: dict[str, Any] = convert_floats_to_decimals({
            **self.model_dump(mode="json", exclude_none=True),
            "pk": self.pk,
            "sk": self.sk,
            "entity_type": "LeadCapture",
        })
        return item

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> Capture:
        return cls.model_validate(convert_decimals(item))


class CaptureFilters(BaseModel):
    agent_id: str | None = None
    form_slug: str | None = None
    status: str | None = None
    #: Test captures from dashboard chat are hidden unless asked for
    include_tests: bool = False
    since: datetime | None = None
    until: datetime | None = None


class CapturePage(BaseModel):
    items: list[Capture]
    next_cursor: str | None = None
    #: Captures hidden by the plan limit, for the upgrade banner
    locked_count: int = 0


class LeadUsage(BaseModel):
    month: str
    forms: int
    forms_limit: int
    captures: int
    captures_limit: int


class LeadFileResponse(BaseModel):
    """What the uploader gets back: the id to put in the form's answer."""

    file_id: str
    filename: str
    content_type: str
    size_bytes: int

    @classmethod
    def of(cls, lead_file: LeadFile) -> LeadFileResponse:
        return cls(file_id=lead_file.file_id, filename=lead_file.filename, content_type=lead_file.content_type,
                   size_bytes=lead_file.size_bytes)


class FileDownload(BaseModel):
    url: str


class UpdateCaptureRequest(BaseModel):
    status: str


class LeadSettingsRequest(BaseModel):
    statuses: list[LeadStatus] = Field(min_length=1, max_length=20)
    #: For each removed status that captures still have, the status to move them to
    replacements: dict[str, str] = Field(default_factory=dict)


class CreateLeadFormRequest(LeadFormFields):
    slug: str
