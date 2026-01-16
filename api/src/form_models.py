from enum import Enum
from pydantic import BaseModel


class FormInputType(Enum):
    TEXT = "text"
    TEXT_AREA = "text_area"
    PASSWORD = "password"
    SELECT = "select"
    CHOICE = "choice"
    
class FormInput(BaseModel):
    input_type: FormInputType
    name: str
    label: str
    value: None | str = None
    values: None | list[str] = None
    attr: None | dict[str, str] = None

class Form(BaseModel):
    form_name: str
    submit_path: str
    form_inputs: list[FormInput]
    
    