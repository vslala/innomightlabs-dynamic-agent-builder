"""Public downloads API router."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from src.downloads.models import PluginDownloadDetail, PluginDownloadsResponse
from src.downloads.service import (
    DownloadsConfigurationError,
    DownloadsService,
    PluginDownloadNotFoundError,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/downloads", tags=["downloads"])


def get_downloads_service() -> DownloadsService:
    return DownloadsService()


@router.get("/plugins", response_model=PluginDownloadsResponse)
def list_plugin_downloads(
    service: Annotated[DownloadsService, Depends(get_downloads_service)],
) -> PluginDownloadsResponse:
    try:
        return PluginDownloadsResponse(plugins=service.list_plugins())
    except DownloadsConfigurationError as exc:
        log.warning("Downloads are unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="Downloads are temporarily unavailable") from exc


@router.get("/plugins/{plugin_id}", response_model=PluginDownloadDetail)
def get_plugin_download(
    plugin_id: str,
    service: Annotated[DownloadsService, Depends(get_downloads_service)],
) -> PluginDownloadDetail:
    try:
        return service.get_plugin_detail(plugin_id)
    except PluginDownloadNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Plugin not found") from exc
    except DownloadsConfigurationError as exc:
        log.warning("Downloads are unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="Downloads are temporarily unavailable") from exc
