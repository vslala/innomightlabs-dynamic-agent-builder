"""Starting an automation run away from the request that asked for it: a local task, or the async job Lambda."""

from __future__ import annotations

import asyncio
import json
import logging

import boto3

from src.accounts.owner import Owner
from src.automations.errors import AutomationValidationError
from src.automations.runner import AutomationRunner
from src.config import settings

log = logging.getLogger(__name__)


def invoke_automation_run_async(run_id: str, automation_id: str, owner: Owner) -> None:
    """Runs as the automation's owner; the Lambda finds them again from the automation in its account."""
    if settings.async_job_backend != "lambda":
        log.info("Automation run will execute in local background task: %s", run_id)
        asyncio.create_task(AutomationRunner().execute_run(run_id, owner))
        return

    function_name = settings.async_job_lambda_name
    if not function_name:
        raise AutomationValidationError("ASYNC_JOB_LAMBDA_NAME is required when ASYNC_JOB_BACKEND=lambda")

    client = boto3.client("lambda", region_name=settings.aws_region)
    response = client.invoke(
        FunctionName=function_name,
        InvocationType="Event",
        Payload=json.dumps(
            {
                "automation_run": {
                    "run_id": run_id,
                    "automation_id": automation_id,
                    "account_id": owner.account_id,
                }
            }
        ).encode("utf-8"),
    )
    log.info("Invoked Lambda async for automation run %s, status: %s", run_id, response["StatusCode"])
