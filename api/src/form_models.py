from enum import Enum
from typing import Union
from pydantic import BaseModel


class FormInputType(Enum):
    TEXT = "text"
    TEXT_AREA = "text_area"
    PASSWORD = "password"
    SELECT = "select"
    CHOICE = "choice"


class SelectOption(BaseModel):
    """Option for select inputs with value and display label."""
    value: str
    label: str


class FormInput(BaseModel):
    input_type: FormInputType
    name: str
    label: str
    value: None | str = None
    # Support both simple string values and value/label pairs
    values: None | list[str] = None
    options: None | list[SelectOption] = None  # New: for value/label pairs
    attr: None | dict[str, str] = None


class Form(BaseModel):
    form_name: str
    submit_path: str
    form_inputs: list[FormInput]
    
    