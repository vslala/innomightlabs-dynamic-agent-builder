"""The one-off move of pre-KAN-97 leads into captures: every lead lands in its agent's account, once."""

import importlib.util
import sys
from pathlib import Path

from src.agents.models import Agent
from src.agents.repository import AgentRepository
from src.leads.models import CaptureFilters
from src.leads.service import LeadsService
from tests.mock_data import TEST_USER_EMAIL, account_for, agent_fields

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "migrate_leads_to_captures.py"


def load_script():
    spec = importlib.util.spec_from_file_location("migrate_leads_to_captures", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def legacy_lead(agent_id: str, lead_id: str, actor_email: str, created_at: str) -> dict:
    return {
        "pk": f"Agent#{agent_id}",
        "sk": f"Lead#{created_at}#{lead_id}",
        "entity_type": "LeadSubmission",
        "lead_id": lead_id,
        "agent_id": agent_id,
        "owner_email": TEST_USER_EMAIL,
        "conversation_id": "conv-1",
        "actor_email": actor_email,
        "actor_id": actor_email,
        "form_label": "Request a demo",
        "answers": [
            {"field_id": "name", "label": "Name", "value": "Jane"},
            {"field_id": "email", "label": "Work email", "value": "jane@acme.com"},
        ],
        "created_at": created_at,
    }


def test_legacy_leads_move_into_their_agents_account_once(dynamodb_table):
    agent = AgentRepository().save(Agent(agent_name="Site agent", agent_architecture="krishna-memgpt",
                                         agent_provider="Bedrock", agent_persona="Hi", **agent_fields(TEST_USER_EMAIL)))
    dynamodb_table.put_item(Item=legacy_lead(agent.agent_id, "lead1", "jane@acme.com", "2026-03-01T10:00:00+00:00"))
    dynamodb_table.put_item(Item=legacy_lead(agent.agent_id, "lead2", TEST_USER_EMAIL, "2026-03-02T10:00:00+00:00"))
    dynamodb_table.put_item(Item=legacy_lead("gone-agent", "lead3", "bob@acme.com", "2026-03-03T10:00:00+00:00"))
    script = load_script()

    dry_run = script.migrate(apply=False)
    assert dry_run["would move"] == 2 and dry_run["skipped: agent no longer exists"] == 1

    applied = script.migrate(apply=True)
    assert applied["moved"] == 2

    account = account_for(TEST_USER_EMAIL)
    captures = LeadsService().list_captures(account, CaptureFilters(include_tests=True), limit=10).items
    assert [(capture.capture_id, capture.source) for capture in captures] == [("lead2", "dashboard"),
                                                                            ("lead1", "widget")]
    jane = captures[1]
    assert jane.answers == {"name": "Jane", "email": "jane@acme.com"}
    assert jane.form_name == "Request a demo" and jane.month_seq is None

    again = script.migrate(apply=True)
    assert again["found"] == 1, "moved leads are deleted; only the orphan is left"
