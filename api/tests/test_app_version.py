from __future__ import annotations

from fastapi.testclient import TestClient

from src.config import settings
from src.config.settings import Settings


def test_app_version_defaults_to_dev(monkeypatch):
    monkeypatch.delenv("APP_VERSION", raising=False)

    assert Settings.from_env().app_version == "dev"


def test_app_version_is_read_from_the_deploy_environment(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "1.0.3")

    assert Settings.from_env().app_version == "1.0.3"


def test_health_reports_the_deployed_version(test_client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "app_version", "1.2.0")

    response = test_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "version": "1.2.0"}
