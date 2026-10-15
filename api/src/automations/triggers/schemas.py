from __future__ import annotations

from src.automations.models import AutomationNode, AutomationNodeType
from src.automations.triggers.models import ANY
from src.form_models import Form, FormInput, FormInputType, SelectOption, SmartSuggestionConfig


def _entry_step_input(nodes: list[AutomationNode]) -> list[FormInput]:
    """Only ask which step to enter when the graph has more than one start.

    A single-start automation has exactly one answer, so the builder supplies it
    and the field is noise.
    """
    start_nodes = [node for node in nodes if node.type == AutomationNodeType.START]
    if len(start_nodes) <= 1:
        return []
    return [
        FormInput(
            input_type=FormInputType.SELECT,
            name="entry_node_id",
            label="Entry step",
            options=[
                SelectOption(value=node.node_id, label=node.name) for node in start_nodes
            ],
        )
    ]


def build_schedule_trigger_form(nodes: list[AutomationNode], submit_path: str = "") -> Form:
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
            *_entry_step_input(nodes),
            FormInput(
                input_type=FormInputType.TEXT,
                name="cron_expression",
                label="Repeat (cron expression)",
                smart_suggestion=SmartSuggestionConfig(
                    suggestion_type="cron_expression",
                    button_label="Suggest",
                    prompt_placeholder="Every weekday at 9 AM",
                ),
                attr={
                    "placeholder": "0 9 * * 1-5",
                    "optional": "true",
                    "help_text": (
                        "To run repeatedly. Standard 5-field cron: minute hour day month weekday. "
                        "Fill this or Run once at, not both."
                    ),
                },
            ),
            FormInput(
                input_type=FormInputType.TEXT,
                name="run_at",
                label="Run once at",
                attr={
                    "placeholder": "2026-10-10T09:00",
                    "optional": "true",
                    "help_text": (
                        "To run a single time, then stop. A date and time (ISO 8601) in the timezone below. "
                        "Cron can't do this: it has no year, so a dated cron repeats every year."
                    ),
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
                    "help_text": (
                        "Optional fixed values passed to every scheduled run. Steps read them as "
                        "{{ input.<key> }}; the values themselves are used as typed."
                    ),
                    "empty_text": "No input values will be passed to the scheduled automation.",
                    "key_placeholder": "topic",
                    "value_placeholder": "AI agent news",
                    "add_label": "Add input",
                },
            ),
        ],
    )


def build_manual_trigger_form(nodes: list[AutomationNode], submit_path: str = "") -> Form:
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
            *_entry_step_input(nodes),
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


def build_lead_captured_trigger_form(
    nodes: list[AutomationNode],
    forms: list[SelectOption],
    agents: list[SelectOption],
    submit_path: str = "",
) -> Form:
    """`forms` and `agents` are the account's, as options: the slug or agent id, and its name."""
    return Form(
        form_name="Lead Captured Trigger",
        submit_path=submit_path,
        form_inputs=[
            FormInput(
                input_type=FormInputType.TEXT,
                name="name",
                label="Name",
                attr={"placeholder": "Send new leads to the CRM"},
            ),
            *_entry_step_input(nodes),
            FormInput(
                input_type=FormInputType.SELECT,
                name="form_slug",
                label="Lead form",
                value=ANY,
                options=[SelectOption(value=ANY, label="Any form"), *forms],
                attr={"help_text": "Steps read the lead as {{ trigger.lead.answers.<field> }}."},
            ),
            FormInput(
                input_type=FormInputType.SELECT,
                name="agent_id",
                label="Captured by",
                value=ANY,
                options=[SelectOption(value=ANY, label="Any agent"), *agents],
            ),
            FormInput(
                input_type=FormInputType.SELECT,
                name="include_test_captures",
                label="Test leads",
                value="false",
                options=[
                    SelectOption(value="false", label="Ignore leads from dashboard chat"),
                    SelectOption(value="true", label="Run for leads from dashboard chat too"),
                ],
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
