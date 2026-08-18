import logging
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Attr, Key

from src.a2a.models import A2ATask
from src.config import settings
from src.db import get_dynamodb_resource

log = logging.getLogger(__name__)


class A2ATaskRepository:
    """Repository for Agent2Agent task records."""

    def __init__(self) -> None:
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, task: A2ATask) -> A2ATask:
        task.updated_at = datetime.now(timezone.utc)
        self.table.put_item(Item=task.to_dynamo_item())
        log.info("Saved A2A task %s for agent %s", task.task_id, task.agent_id)
        return task

    def find_by_id(self, *, agent_id: str, task_id: str) -> A2ATask | None:
        response = self.table.get_item(
            Key={
                "pk": f"A2A#Agent#{agent_id}",
                "sk": f"Task#{task_id}",
            }
        )
        item = response.get("Item")
        if not item:
            return None
        return A2ATask.from_dynamo_item(item)

    def find_by_agent_and_client(self, *, agent_id: str, client_key_id: str) -> list[A2ATask]:
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"A2A#Agent#{agent_id}")
            & Key("sk").begins_with("Task#"),
            FilterExpression=Attr("entity_type").eq("A2ATask")
            & Attr("client_key_id").eq(client_key_id),
        )
        tasks = [A2ATask.from_dynamo_item(item) for item in response.get("Items", [])]
        tasks.sort(key=lambda task: task.created_at, reverse=True)
        return tasks

    def find_by_agent(self, *, agent_id: str) -> list[A2ATask]:
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"A2A#Agent#{agent_id}")
            & Key("sk").begins_with("Task#"),
            FilterExpression=Attr("entity_type").eq("A2ATask"),
        )
        tasks = [A2ATask.from_dynamo_item(item) for item in response.get("Items", [])]
        tasks.sort(key=lambda task: task.created_at, reverse=True)
        return tasks
