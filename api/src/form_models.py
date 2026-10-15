from collections.abc import Mapping
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field


class FormInputType(Enum):
    TEXT = "text"
    TEXT_AREA = "text_area"
    PASSWORD = "password"
    SELECT = "select"
    SEARCH = "search"
    CHOICE = "choice"
    FILE_UPLOAD = "file_upload"
    KEY_VALUE = "key_value"


class SelectOption(BaseModel):
    """Option for select inputs with value and display label."""
    value: str = Field(description="What is stored when it's picked.")
    label: str = Field(description="What the person sees.")
    group: str | None = Field(
        None, description="What the option belongs to, such as a model's provider. Read by `options_filter`."
    )


class FormOptionsSource(BaseModel):
    """Dynamic option source metadata for inputs such as select and choice."""

    type: str = Field(description="Dashboard forms only: where the options come from, such as `agents`.")
    mode: Literal["hydrate", "lazy"] = Field("hydrate", description="Load the options with the form, or when opened.")
    endpoint: str | None = Field(None, description="Not used yet.")


class FormOptionsFilter(BaseModel):
    """Offer only the options whose `group` is another field's current value.

    The model field filters by the provider field this way, so picking a provider
    narrows the models to that provider's. Ungrouped options are always offered.
    The SPA applies the same rule as the user types (`optionsFilter.ts`).
    """

    field: str = Field(description="Dashboard forms only: the field whose value picks the options' group.")

    def apply(self, options: list[SelectOption], values: Mapping[str, Any]) -> list[SelectOption]:
        selected = values.get(self.field)
        return [option for option in options if option.group is None or option.group == selected]


class FormInputValidationFormat(str, Enum):
    EMAIL = "email"
    PHONE = "phone"
    URL = "url"
    NUMBER = "number"
    DATE = "date"  # ISO 8601, YYYY-MM-DD


class FormInputValidation(BaseModel):
    """Declarative validation metadata for schema-driven form inputs.

    `form_validation.validate_form_value` enforces it; renderers only use it as hints.
    """

    format: FormInputValidationFormat | None = Field(
        None, description="What a text value must be: email, phone, url, number, or date (YYYY-MM-DD)."
    )
    multiple: bool = Field(False, description="For `format: email`: a list of addresses.")
    separator: str = Field(",", description="What separates the addresses of a `multiple` list.")
    min_items: int | None = Field(None, description="The fewest values: emails in a list, checked choices, files.")
    max_items: int | None = Field(None, description="The most values: emails in a list, checked choices, files.")
    min_length: int | None = Field(None, description="The fewest characters a text value may have.")
    max_length: int | None = Field(None, description="The most characters a text value may have.")
    pattern: str | None = Field(None, description="A regular expression the whole value must match.")
    minimum: float | None = Field(None, description="For `format: number`: the smallest allowed.")
    maximum: float | None = Field(None, description="For `format: number`: the largest allowed.")
    max_file_bytes: int | None = Field(None, description="For `file_upload`: the largest file, in bytes.")
    accept: list[str] | None = Field(
        None, description="For `file_upload`: the MIME types accepted, checked against the file's contents."
    )


class SmartSuggestionConfig(BaseModel):
    """Optional AI suggestion metadata for text-like form inputs."""

    enabled: bool = Field(True, description="Whether the Suggest button shows.")
    suggestion_type: str = Field(description="Dashboard forms only: which suggestion strategy drafts the value.")
    button_label: str = Field("Suggest", description="The button's label.")
    prompt_placeholder: str | None = Field(None, description="Placeholder for the prompt the person types.")


class FormInput(BaseModel):
    """One field of a form. Every form on the platform uses this: dashboard settings, skill installs, chat forms and
    lead forms. Required unless `attr.optional` is "true"."""

    input_type: FormInputType = Field(
        description="How it's shown: text, text_area, password, select, search, choice, file_upload or key_value."
    )
    name: str = Field(description="The field's id: what its answer is stored under.")
    label: str = Field(description="What the person sees above the field.")
    value: None | str = Field(None, description="The value it starts with.")
    values: None | list[str] = Field(None, description="Choices whose label is their value, for select and choice.")
    options: None | list[SelectOption] = Field(None, description="Choices with a value and a label, for select and choice.")
    options_source: None | FormOptionsSource = Field(None, description="Dashboard forms only: options loaded at runtime.")
    options_filter: None | FormOptionsFilter = Field(
        None, description="Dashboard forms only: offer the options matching another field's value."
    )
    validation: None | FormInputValidation = Field(None, description="What a valid value is; the API enforces it.")
    smart_suggestion: None | SmartSuggestionConfig = Field(
        None, description="Dashboard forms only: an AI Suggest button for the field."
    )
    attr: None | dict[str, str] = Field(
        None,
        description="Hints as text: optional (\"true\"), help_text, placeholder, variant (radio or checkbox for "
        "choice), agent_hint (lead forms: guidance only the agent sees).",
    )

    @property
    def is_optional(self) -> bool:
        """Whether this input may be omitted or left blank on submit.

        Declared as `attr={"optional": "true"}` -- the convention already used
        by the agent and provider schemas.
        """
        return (self.attr or {}).get("optional", "").strip().lower() == "true"


class Form(BaseModel):
    form_name: str
    submit_path: str
    form_inputs: list[FormInput]
    
    
