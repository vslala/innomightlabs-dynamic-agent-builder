"""An agent's instructions are edited as Markdown, in both the create and the update form."""

from src.agents.schemas import UPDATE_AGENT_FORM, get_create_agent_form, get_update_agent_form
from src.form_models import FormInputType


def instructions_of(form):
    return next(field for field in form.form_inputs if field.name == "agent_persona")


def test_instructions_are_a_markdown_field_with_their_suggestion_everywhere():
    for form in (get_create_agent_form(), get_update_agent_form("agent-1"), UPDATE_AGENT_FORM):
        field = instructions_of(form)
        assert field.input_type is FormInputType.MARKDOWN
        assert field.smart_suggestion is not None, "Suggest instructions stays on the field"
        assert form.model_dump(mode="json")["form_inputs"][form.form_inputs.index(field)]["input_type"] == "markdown"
