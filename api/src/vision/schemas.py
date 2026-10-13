"""The Settings form for the account's image reading."""

from __future__ import annotations

from src.form_models import Form, FormInput, FormInputType, FormOptionsFilter, FormOptionsSource, SelectOption
from src.form_options import FormOptionSourceType
from src.vision.models import VisionSettings


def build_vision_settings_form(vision_settings: VisionSettings | None = None) -> Form:
    return Form(
        form_name="Image Reading Settings",
        submit_path="/vision/settings",
        form_inputs=[
            FormInput(
                input_type=FormInputType.SELECT,
                name="enabled",
                label="Image reading",
                value="true" if vision_settings and vision_settings.enabled else "false",
                options=[
                    SelectOption(value="true", label="Enabled"),
                    SelectOption(value="false", label="Disabled"),
                ],
            ),
            FormInput(
                input_type=FormInputType.SELECT,
                name="provider_name",
                label="Provider",
                value=vision_settings.provider_name if vision_settings else None,
                options_source=FormOptionsSource(type=FormOptionSourceType.AGENT_MODEL_PROVIDERS),
            ),
            FormInput(
                input_type=FormInputType.SEARCH,
                name="model_name",
                label="Vision model",
                value=vision_settings.model_name if vision_settings else None,
                options_source=FormOptionsSource(type=FormOptionSourceType.VISION_MODELS),
                options_filter=FormOptionsFilter(field="provider_name"),
            ),
        ],
    )
