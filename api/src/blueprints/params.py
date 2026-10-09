"""The types a blueprint param can have. Each type says how a value is read and how it's asked for in the run form,
so the spec, the validator and the form read them from here rather than branching on the type's name."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Optional

import src.form_models as form_models

if TYPE_CHECKING:
    from src.blueprints.spec import ParamSpec

URL = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.IGNORECASE)
TRUE_WORDS = {"true", "yes", "on", "1"}
FALSE_WORDS = {"false", "no", "off", "0"}


class ParamType:
    """A single line of text. The others change what they need to."""

    name = "string"
    input_type = form_models.FormInputType.TEXT
    #: Only a `choice` lists its values.
    takes_options = False
    placeholder: Optional[str] = None

    def coerce(self, spec: "ParamSpec", value: Any) -> tuple[Any, Optional[str]]:
        """The value as this type, or an error that reads after "The value …"."""
        return str(value).strip(), None

    def form_values(self, spec: "ParamSpec") -> Optional[list[str]]:
        return None


class Text(ParamType):
    name = "text"
    input_type = form_models.FormInputType.TEXT_AREA

    def coerce(self, spec: "ParamSpec", value: Any) -> tuple[Any, Optional[str]]:
        return str(value), None


class Url(ParamType):
    name = "url"
    placeholder = "https://example.com"

    def coerce(self, spec: "ParamSpec", value: Any) -> tuple[Any, Optional[str]]:
        text = str(value).strip()
        if not URL.match(text):
            return None, "must be a web address starting with http:// or https://."
        return text, None


class Integer(ParamType):
    name = "integer"

    def coerce(self, spec: "ParamSpec", value: Any) -> tuple[Any, Optional[str]]:
        try:
            return int(str(value).strip()), None
        except ValueError:
            return None, "must be a whole number."


class Boolean(ParamType):
    name = "boolean"
    input_type = form_models.FormInputType.SELECT

    def coerce(self, spec: "ParamSpec", value: Any) -> tuple[Any, Optional[str]]:
        if isinstance(value, bool):
            return value, None
        word = str(value).strip().lower()
        if word in TRUE_WORDS | FALSE_WORDS:
            return word in TRUE_WORDS, None
        return None, "must be true or false."

    def form_values(self, spec: "ParamSpec") -> Optional[list[str]]:
        return ["true", "false"]


class Choice(ParamType):
    name = "choice"
    input_type = form_models.FormInputType.SELECT
    takes_options = True

    def coerce(self, spec: "ParamSpec", value: Any) -> tuple[Any, Optional[str]]:
        text = str(value).strip()
        if text not in spec.options:
            return None, f"must be one of: {', '.join(spec.options)}."
        return text, None

    def form_values(self, spec: "ParamSpec") -> Optional[list[str]]:
        return list(spec.options)


PARAM_TYPES: dict[str, ParamType] = {
    param_type.name: param_type for param_type in (ParamType(), Text(), Url(), Boolean(), Integer(), Choice())
}


def param_type(spec: "ParamSpec") -> ParamType:
    return PARAM_TYPES[spec.type]
