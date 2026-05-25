import json

import pytest
from fastapi import HTTPException

from src.config import settings
from src.automations.router import invoke_automation_run_async
from src.automations.service import AutomationValidationError
from src.knowledge.router import _invoke_crawl_async


class FakeLambdaClient:
    def __init__(self):
        self.calls = []

    def invoke(self, **kwargs):
        self.calls.append(kwargs)
        return {"StatusCode": 202}


def test_automation_dispatch_invokes_configured_lambda(monkeypatch):
    fake_client = FakeLambdaClient()
    monkeypatch.setattr(settings, "async_job_backend", "lambda")
    monkeypatch.setattr(settings, "async_job_lambda_name", "worker-lambda")
    monkeypatch.setattr(settings, "aws_region", "us-east-1")
    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: fake_client)

    invoke_automation_run_async("run-1", "automation-1", "user@example.com")

    assert len(fake_client.calls) == 1
    call = fake_client.calls[0]
    assert call["FunctionName"] == "worker-lambda"
    assert call["InvocationType"] == "Event"
    assert json.loads(call["Payload"].decode("utf-8")) == {
        "automation_run": {
            "run_id": "run-1",
            "automation_id": "automation-1",
            "user_email": "user@example.com",
        }
    }


def test_automation_dispatch_requires_lambda_name(monkeypatch):
    monkeypatch.setattr(settings, "async_job_backend", "lambda")
    monkeypatch.setattr(settings, "async_job_lambda_name", "")

    with pytest.raises(AutomationValidationError, match="ASYNC_JOB_LAMBDA_NAME"):
        invoke_automation_run_async("run-1", "automation-1", "user@example.com")


def test_crawl_dispatch_invokes_configured_lambda(monkeypatch):
    fake_client = FakeLambdaClient()
    monkeypatch.setattr(settings, "async_job_lambda_name", "worker-lambda")
    monkeypatch.setattr(settings, "aws_region", "us-east-1")
    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: fake_client)

    _invoke_crawl_async("job-1", "kb-1", "user@example.com")

    assert len(fake_client.calls) == 1
    call = fake_client.calls[0]
    assert call["FunctionName"] == "worker-lambda"
    assert call["InvocationType"] == "Event"
    assert json.loads(call["Payload"]) == {
        "crawl_job": {
            "job_id": "job-1",
            "kb_id": "kb-1",
            "user_email": "user@example.com",
        }
    }


def test_crawl_dispatch_requires_lambda_name(monkeypatch):
    monkeypatch.setattr(settings, "async_job_lambda_name", "")

    with pytest.raises(HTTPException) as exc_info:
        _invoke_crawl_async("job-1", "kb-1", "user@example.com")

    assert exc_info.value.status_code == 503
    assert "ASYNC_JOB_LAMBDA_NAME" in str(exc_info.value.detail)
