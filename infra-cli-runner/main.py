import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from src.infra_cli_runner.browser import get_browser_renderer
from src.infra_cli_runner.filesystem import get_file_system_service
from src.infra_cli_runner.mcp_servers import get_mcp_server_pool
from src.infra_cli_runner.router import router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    pool = get_mcp_server_pool()
    reaper = asyncio.create_task(pool.run_reaper())
    sweeper = asyncio.create_task(get_file_system_service().run_sweeper())
    try:
        yield
    finally:
        for task in (reaper, sweeper):
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        await pool.close()
        await get_browser_renderer().close()


app = FastAPI(title="InnomightLabs Infra CLI Runner", version="0.4.0", lifespan=lifespan)
app.include_router(router)

__all__ = ["app"]
