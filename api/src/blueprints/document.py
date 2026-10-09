"""The blueprint document: its metadata, params, outputs and resources.

`resources` accepts the spec model of every kind in `RESOURCE_KINDS`, so adding a kind there is all it takes for a
blueprint to accept it. The parts are described in `spec.py`.
"""

from typing import Annotated, Literal, Union

from pydantic import ConfigDict, Field

from src.blueprints.kinds import RESOURCE_KINDS
from src.blueprints.spec import Metadata, OutputSpec, ParamSpec, ResourceName, Strict

#: The spec models of every kind, as one union chosen by `kind`.
Resource = Annotated[  # type: ignore[valid-type]
    Union[tuple(kind.spec_model for kind in RESOURCE_KINDS)],
    Field(discriminator="kind"),
]


class Blueprint(Strict):
    """A description of a solution on InnomightLabs: the resources to create and how they connect."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    api_version: Literal["innomight/v1"] = Field(
        alias="apiVersion", description="Which version of the blueprint rules this document follows."
    )
    kind: Literal["Blueprint"] = Field(description="Always Blueprint. Marks the document type.")
    metadata: Metadata = Field(description="Who the blueprint is and what it's for.")
    params: dict[ResourceName, ParamSpec] = Field(
        default_factory=dict,
        description="Values the person running the blueprint fills in. Each becomes an input in the run form.",
    )
    resources: dict[ResourceName, Resource] = Field(  # type: ignore[valid-type]
        min_length=1,
        description="Everything the blueprint creates. The key is the resource's local name, used for references.",
    )
    outputs: dict[ResourceName, OutputSpec] = Field(
        default_factory=dict, description="Values shown after a successful apply, such as the embed snippet."
    )
