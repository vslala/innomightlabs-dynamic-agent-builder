from fastapi.testclient import TestClient

from src.downloads.models import PluginDownloadDetail, PluginDownloadSummary
from src.downloads.router import get_downloads_service
from src.downloads.service import PluginDownloadNotFoundError


class FakeDownloadsService:
    def list_plugins(self) -> list[PluginDownloadSummary]:
        return [
            PluginDownloadSummary(
                id="vscode",
                name="Innomight VS Code",
                kind="Editor plugin",
                tagline="Build automations from your editor.",
                description="Create and test Innomight workflows directly inside VS Code.",
                version="0.0.1",
                platform="VS Code",
                filename="innomightlabs-code-assist-0.0.1.vsix",
                download_url="https://example.com/vscode.vsix",
                icon_url="https://example.com/icon.svg",
                size_bytes=123,
                sha256="abc123",
            )
        ]

    def get_plugin_detail(self, plugin_id: str) -> PluginDownloadDetail:
        if plugin_id != "vscode":
            raise PluginDownloadNotFoundError(plugin_id)

        return PluginDownloadDetail(
            **self.list_plugins()[0].model_dump(),
            readme_markdown="# Innomight VS Code\n\nInstall the extension.",
        )


def test_list_plugin_downloads_is_public(test_client: TestClient):
    from main import app

    app.dependency_overrides[get_downloads_service] = lambda: FakeDownloadsService()
    try:
        response = test_client.get("/downloads/plugins")
    finally:
        app.dependency_overrides.pop(get_downloads_service, None)

    assert response.status_code == 200
    body = response.json()
    assert body["plugins"][0]["id"] == "vscode"
    assert body["plugins"][0]["download_url"] == "https://example.com/vscode.vsix"


def test_get_plugin_download_detail(test_client: TestClient):
    from main import app

    app.dependency_overrides[get_downloads_service] = lambda: FakeDownloadsService()
    try:
        response = test_client.get("/downloads/plugins/vscode")
    finally:
        app.dependency_overrides.pop(get_downloads_service, None)

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "innomightlabs-code-assist-0.0.1.vsix"
    assert "Install the extension" in body["readme_markdown"]


def test_get_plugin_download_detail_404(test_client: TestClient):
    from main import app

    app.dependency_overrides[get_downloads_service] = lambda: FakeDownloadsService()
    try:
        response = test_client.get("/downloads/plugins/missing")
    finally:
        app.dependency_overrides.pop(get_downloads_service, None)

    assert response.status_code == 404
