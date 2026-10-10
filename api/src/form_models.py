from collections.abc import Mapping
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel


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
    value: str
    label: str
    #: What the option belongs to, e.g. a model's provider. Read by `FormOptionsFilter`.
    group: str | None = None


class FormOptionsSource(BaseModel):
    """Dynamic option source metadata for inputs such as select and choice."""

    type: str
    mode: Literal["hydrate", "lazy"] = "hydrate"
    endpoint: str | None = None


class FormOptionsFilter(BaseModel):
    """Offer only the options whose `group` is another field's current value.

    The model field filters by the provider field this way, so picking a provider
    narrows the models to that provider's. Ungrouped options are always offered.
    The SPA applies the same rule as the user types (`optionsFilter.ts`).
    """

    field: str

    def apply(self, options: list[SelectOption], values: Mapping[str, Any]) -> list[SelectOption]:
        selected = values.get(self.field)
        return [option for option in options if option.group is None or option.group == selected]


class FormInputValidationFormat(str, Enum):
    EMAIL = "email"


class FormInputValidation(BaseModel):
    """Declarative validation metadata for schema-driven form inputs."""

    format: FormInputValidationFormat | None = None
    multiple: bool = False
    separator: str = ","
    min_items: int | None = None
    max_items: int | None = None


class SmartSuggestionConfig(BaseModel):
    """Optional AI suggestion metadata for text-like form inputs."""

    enabled: bool = True
    suggestion_type: str
    button_label: str = "Suggest"
    prompt_placeholder: str | None = None


class FormInput(BaseModel):
    input_type: FormInputType
    name: str
    label: str
    value: None | str = None
    # Support both simple string values and value/label pairs
    values: None | list[str] = None
    options: None | list[SelectOption] = None  # New: for value/label pairs
    options_source: None | FormOptionsSource = None
    options_filter: None | FormOptionsFilter = None
    validation: None | FormInputValidation = None
    smart_suggestion: None | SmartSuggestionConfig = None
    attr: None | dict[str, str] = None

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
    
    
