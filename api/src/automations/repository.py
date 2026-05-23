"""Repository for automation entities using the project single-table pattern."""

import base64
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

from boto3.dynamodb.conditions import Key

from src.automations.models import (
    Automation,
    AutomationEdge,
    AutomationNode,
    AutomationRun,
    AutomationRunNodeResult,
    AutomationSkill,
    AutomationStatus,
    AutomationTrigger,
)
from src.config import settings
from src.crypto import decrypt
from src.db import get_dynamodb_resource

log = logging.getLogger(__name__)


class AutomationRepository:
    """DynamoDB access for automations, graphs, triggers, and runs."""

    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save_automation(self, automation: Automation) -> Automation:
        existing = self.find_automation_by_id(automation.automation_id, automation.created_by)
        if existing:
            automation.created_at = existing.created_at
            automation.updated_at = datetime.now(timezone.utc)
            automation.version = existing.version + 1
        self.table.put_item(Item=automation.to_dynamo_item())
        log.info("Saved automation %s for user %s", automation.automation_id, automation.created_by)
        return automation

    def find_automation_by_id(self, automation_id: str, user_email: str) -> Optional[Automation]:
        response = self.table.get_item(
            Key={"pk": f"User#{user_email}", "sk": f"Automation#{automation_id}"}
        )
        item = response.get("Item")
        if not item:
            return None
        return Automation.from_dynamo_item(item)

    def find_automations_by_user(self, user_email: str, include_deleted: bool = False) -> list[Automation]:
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"User#{user_email}")
            & Key("sk").begins_with("Automation#")
        )
        automations = [
            Automation.from_dynamo_item(item)
            for item in response.get("Items", [])
            if item.get("entity_type") == "Automation"
        ]
        if not include_deleted:
            automations = [
                automation for automation in automations if automation.status != AutomationStatus.DELETED
            ]
        automations.sort(key=lambda automation: automation.created_at, reverse=True)
        return automations

    def soft_delete_automation(self, automation_id: str, user_email: str) -> bool:
        try:
            self.table.update_item(
                Key={"pk": f"User#{user_email}", "sk": f"Automation#{automation_id}"},
                UpdateExpression="SET #status = :status, updated_at = :updated_at",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":status": AutomationStatus.DELETED.value,
                    ":updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            return True
        except Exception:
            log.exception("Failed to soft delete automation %s", automation_id)
            return False

    def save_node(self, node: AutomationNode) -> AutomationNode:
        existing = self.find_node(node.automation_id, node.node_id)
        if existing:
            node.created_at = existing.created_at
            node.updated_at = datetime.now(timezone.utc)
        self.table.put_item(Item=node.to_dynamo_item())
        return node

    def save_edge(self, edge: AutomationEdge) -> AutomationEdge:
        existing = self.find_edge(edge.automation_id, edge.edge_id)
        if existing:
            edge.created_at = existing.created_at
            edge.updated_at = datetime.now(timezone.utc)
        self.table.put_item(Item=edge.to_dynamo_item())
        return edge

    def save_trigger(self, trigger: AutomationTrigger) -> AutomationTrigger:
        existing = self.find_trigger(trigger.automation_id, trigger.trigger_id)
        if existing:
            trigger.created_at = existing.created_at
            trigger.updated_at = datetime.now(timezone.utc)
        self.table.put_item(Item=trigger.to_dynamo_item())
        return trigger

    def find_node(self, automation_id: str, node_id: str) -> Optional[AutomationNode]:
        response = self.table.get_item(
            Key={"pk": f"Automation#{automation_id}", "sk": f"Node#{node_id}"}
        )
        item = response.get("Item")
        return AutomationNode.from_dynamo_item(item) if item else None

    def find_edge(self, automation_id: str, edge_id: str) -> Optional[AutomationEdge]:
        response = self.table.get_item(
            Key={"pk": f"Automation#{automation_id}", "sk": f"Edge#{edge_id}"}
        )
        item = response.get("Item")
        return AutomationEdge.from_dynamo_item(item) if item else None

    def find_trigger(self, automation_id: str, trigger_id: str) -> Optional[AutomationTrigger]:
        response = self.table.get_item(
            Key={"pk": f"Automation#{automation_id}", "sk": f"Trigger#{trigger_id}"}
        )
        item = response.get("Item")
        return AutomationTrigger.from_dynamo_item(item) if item else None

    def get_graph(
        self, automation_id: str
    ) -> tuple[list[AutomationNode], list[AutomationEdge], list[AutomationTrigger]]:
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"Automation#{automation_id}")
        )
        nodes: list[AutomationNode] = []
        edges: list[AutomationEdge] = []
        triggers: list[AutomationTrigger] = []
        for item in response.get("Items", []):
            entity_type = item.get("entity_type")
            if entity_type == "AutomationNode":
                nodes.append(AutomationNode.from_dynamo_item(item))
            elif entity_type == "AutomationEdge":
                edges.append(AutomationEdge.from_dynamo_item(item))
            elif entity_type == "AutomationTrigger":
                triggers.append(AutomationTrigger.from_dynamo_item(item))
        nodes.sort(key=lambda node: node.created_at)
        edges.sort(key=lambda edge: edge.created_at)
        triggers.sort(key=lambda trigger: trigger.created_at)
        return nodes, edges, triggers

    def save_graph(
        self,
        automation_id: str,
        nodes: list[AutomationNode],
        edges: list[AutomationEdge],
        triggers: list[AutomationTrigger],
    ) -> None:
        existing_nodes, existing_edges, existing_triggers = self.get_graph(automation_id)
        new_node_ids = {node.node_id for node in nodes}
        new_edge_ids = {edge.edge_id for edge in edges}
        new_trigger_ids = {trigger.trigger_id for trigger in triggers}

        with self.table.batch_writer() as batch:
            for node in existing_nodes:
                if node.node_id not in new_node_ids:
                    batch.delete_item(Key={"pk": node.pk, "sk": node.sk})
            for edge in existing_edges:
                if edge.edge_id not in new_edge_ids:
                    batch.delete_item(Key={"pk": edge.pk, "sk": edge.sk})
            for trigger in existing_triggers:
                if trigger.trigger_id not in new_trigger_ids:
                    batch.delete_item(Key={"pk": trigger.pk, "sk": trigger.sk})
            for node in nodes:
                batch.put_item(Item=node.to_dynamo_item())
            for edge in edges:
                batch.put_item(Item=edge.to_dynamo_item())
            for trigger in triggers:
                batch.put_item(Item=trigger.to_dynamo_item())

    def delete_node(self, automation_id: str, node_id: str) -> None:
        self.table.delete_item(Key={"pk": f"Automation#{automation_id}", "sk": f"Node#{node_id}"})

    def delete_edge(self, automation_id: str, edge_id: str) -> None:
        self.table.delete_item(Key={"pk": f"Automation#{automation_id}", "sk": f"Edge#{edge_id}"})

    def delete_trigger(self, automation_id: str, trigger_id: str) -> None:
        self.table.delete_item(
            Key={"pk": f"Automation#{automation_id}", "sk": f"Trigger#{trigger_id}"}
        )

    def save_run(self, run: AutomationRun) -> AutomationRun:
        self.table.put_item(Item=run.to_dynamo_item())
        self.table.put_item(Item=run.to_owner_lookup_item())
        return run

    def find_runs_by_automation(
        self, automation_id: str, limit: int = 20, cursor: Optional[str] = None
    ) -> Tuple[list[AutomationRun], Optional[str], bool]:
        query_params = {
            "KeyConditionExpression": Key("pk").eq(f"Automation#{automation_id}")
            & Key("sk").begins_with("Run#"),
            "Limit": limit,
            "ScanIndexForward": False,
        }
        if cursor:
            try:
                query_params["ExclusiveStartKey"] = json.loads(
                    base64.b64decode(cursor).decode("utf-8")
                )
            except Exception:
                log.warning("Invalid run cursor: %s", cursor)
        response = self.table.query(**query_params)
        runs = [AutomationRun.from_dynamo_item(item) for item in response.get("Items", [])]
        last_key = response.get("LastEvaluatedKey")
        next_cursor = (
            base64.b64encode(json.dumps(last_key).encode("utf-8")).decode("utf-8")
            if last_key
            else None
        )
        return runs, next_cursor, last_key is not None

    def find_run_by_id(self, run_id: str, user_email: str) -> Optional[AutomationRun]:
        lookup = self.table.get_item(
            Key={"pk": f"User#{user_email}", "sk": f"AutomationRun#{run_id}"}
        ).get("Item")
        if not lookup:
            return None
        response = self.table.get_item(
            Key={
                "pk": f"Automation#{lookup['automation_id']}",
                "sk": f"Run#{lookup['created_at']}#{run_id}",
            }
        )
        item = response.get("Item")
        return AutomationRun.from_dynamo_item(item) if item else None

    def save_node_result(self, result: AutomationRunNodeResult) -> AutomationRunNodeResult:
        self.table.put_item(Item=result.to_dynamo_item())
        return result

    def find_node_results(self, run_id: str) -> list[AutomationRunNodeResult]:
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"AutomationRun#{run_id}")
            & Key("sk").begins_with("NodeResult#")
        )
        results = [
            AutomationRunNodeResult.from_dynamo_item(item)
            for item in response.get("Items", [])
        ]
        results.sort(key=lambda result: result.started_at)
        return results

    def save_skill(self, skill: AutomationSkill) -> AutomationSkill:
        existing = self.find_skill(skill.automation_id, skill.skill_id)
        if existing:
            skill.enabled_at = existing.enabled_at
            skill.updated_at = datetime.now(timezone.utc)
        self.table.put_item(Item=skill.to_dynamo_item())
        return skill

    def find_skill(self, automation_id: str, skill_id: str) -> Optional[AutomationSkill]:
        response = self.table.get_item(
            Key={"pk": f"Automation#{automation_id}", "sk": f"Skill#{skill_id}"}
        )
        item = response.get("Item")
        return AutomationSkill.from_dynamo_item(item) if item else None

    def list_skills(self, automation_id: str) -> list[AutomationSkill]:
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"Automation#{automation_id}")
            & Key("sk").begins_with("Skill#")
        )
        skills = [
            AutomationSkill.from_dynamo_item(item)
            for item in response.get("Items", [])
            if item.get("entity_type") == "AutomationSkill"
        ]
        skills.sort(key=lambda item: item.enabled_at)
        return skills

    def delete_skill(self, automation_id: str, skill_id: str) -> bool:
        try:
            self.table.delete_item(
                Key={"pk": f"Automation#{automation_id}", "sk": f"Skill#{skill_id}"}
            )
            return True
        except Exception:
            log.exception("Failed deleting automation skill %s/%s", automation_id, skill_id)
            return False

    def get_skill_runtime_config(self, skill: AutomationSkill) -> dict:
        config = dict(skill.config)
        if not skill.encrypted_secrets:
            return config
        secrets = json.loads(decrypt(skill.encrypted_secrets))
        if isinstance(secrets, dict):
            config.update(secrets)
        return config
