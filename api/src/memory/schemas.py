"""Schema-driven forms for Memory module."""

from src.form_models import Form, FormInput, FormInputType, SelectOption
from .models import EvictionPolicy


def get_create_memory_block_form(agent_id: str) -> Form:
    """Form schema for creating a custom memory block."""

    return Form(
        form_name="Create Memory Block",
        submit_path=f"/agents/{agent_id}/memory-blocks",
        form_inputs=[
            FormInput(
                input_type=FormInputType.TEXT,
                name="name",
                label="Block Name",
                attr={
                    "placeholder": "e.g., projects, goals, preferences",
                },
            ),
            FormInput(
                input_type=FormInputType.TEXT,
                name="description",
                label="Description",
                attr={
                    "placeholder": "What information will be stored in this block?",
                },
            ),
            FormInput(
                input_type=FormInputType.TEXT,
                name="word_limit",
                label="Word Limit",
                value="5000",
                attr={
                    "type": "number",
                    "min": "100",
                    "max": "50000",
                },
            ),
            FormInput(
                input_type=FormInputType.SELECT,
                name="eviction_policy",
                label="Overflow Policy",
                options=[
                    SelectOption(value=p.value, label=p.value.upper())
                    for p in EvictionPolicy
                ],
            ),
        ],
    )
