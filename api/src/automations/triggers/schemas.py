from __future__ import annotations

from src.automations.models import AutomationNode, AutomationNodeType
from src.form_models import Form, FormInput, FormInputType, SelectOption, SmartSuggestionConfig


def build_schedule_trigger_form(nodes: list[AutomationNode], submit_path: str = "") -> Form:
    entry_options = [
        SelectOption(value=node.node_id, label=node.name)
        for node in nodes
        if node.type == AutomationNodeType.START
    ]
    return Form(
        form_name="Schedule Trigger",
        submit_path=submit_path,
        form_inputs=[
            FormInput(
                input_type=FormInputType.TEXT,
                name="name",
                label="Name",
                attr={"placeholder": "Weekday cleanup"},
            ),
            FormInput(
                input_type=FormInputType.SELECT,
                name="entry_node_id",
                label="Entry step",
                options=entry_options,
            ),
            FormInput(
                input_type=FormInputType.TEXT,
                name="cron_expression",
                label="Cron expression",
                smart_suggestion=SmartSuggestionConfig(
                    suggestion_type="cron_expression",
                    button_label="Suggest",
                    prompt_placeholder="Every weekday at 9 AM",
                ),
                attr={
                    "placeholder": "0 9 * * 1-5",
                    "help_text": "Standard 5-field cron: minute hour day month weekday.",
                },
            ),
            FormInput(
                input_type=FormInputType.TEXT,
                name="timezone",
                label="Timezone",
                value="UTC",
                attr={"placeholder": "UTC"},
            ),
            FormInput(
                input_type=FormInputType.SELECT,
                name="enabled",
                label="Status",
                value="true",
                options=[
                    SelectOption(value="true", label="Enabled"),
                    SelectOption(value="false", label="Disabled"),
                ],
            ),
            FormInput(
                input_type=FormInputType.KEY_VALUE,
                name="input",
                label="Input",
                attr={
                    "help_text": "Optional values available to the workflow as scheduled run input.",
                    "empty_text": "No input values will be passed to the scheduled automation.",
                    "key_placeholder": "customer_email",
                    "value_placeholder": "{{ input.email }}",
                    "add_label": "Add input",
                },
            ),
        ],
    )


def build_manual_trigger_form(nodes: list[AutomationNode], submit_path: str = "") -> Form:
    entry_options = [
        SelectOption(value=node.node_id, label=node.name)
        for node in nodes
        if node.type == AutomationNodeType.START
    ]
    return Form(
        form_name="Manual Trigger",
        submit_path=submit_path,
        form_inputs=[
            FormInput(
                input_type=FormInputType.TEXT,
                name="name",
                label="Name",
                attr={"placeholder": "Manual run"},
            ),
            FormInput(
                input_type=FormInputType.SELECT,
                name="entry_node_id",
                label="Entry step",
                options=entry_options,
            ),
            FormInput(
                input_type=FormInputType.SELECT,
                name="enabled",
                label="Status",
                value="true",
                options=[
                    SelectOption(value="true", label="Enabled"),
                    SelectOption(value="false", label="Disabled"),
                ],
            ),
        ],
    )
