from enum import Enum
from typing import Literal
from pydantic import BaseModel


class FormInputType(Enum):
    TEXT = "text"
    TEXT_AREA = "text_area"
    PASSWORD = "password"
    SELECT = "select"
    CHOICE = "choice"
    FILE_UPLOAD = "file_upload"


class SelectOption(BaseModel):
    """Option for select inputs with value and display label."""
    value: str
    label: str


class FormOptionsSource(BaseModel):
    """Dynamic option source metadata for inputs such as select and choice."""

    type: str
    mode: Literal["hydrate", "lazy"] = "hydrate"
    endpoint: str | None = None


class FormInput(BaseModel):
    input_type: FormInputType
    name: str
    label: str
    value: None | str = None
    # Support both simple string values and value/label pairs
    values: None | list[str] = None
    options: None | list[SelectOption] = None  # New: for value/label pairs
    options_source: None | FormOptionsSource = None
    attr: None | dict[str, str] = None


class Form(BaseModel):
    form_name: str
    submit_path: str
    form_inputs: list[FormInput]
    
    
