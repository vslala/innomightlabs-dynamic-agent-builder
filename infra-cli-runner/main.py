import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from src.infra_cli_runner.mcp_servers import get_mcp_server_pool
from src.infra_cli_runner.router import router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    pool = get_mcp_server_pool()
    reaper = asyncio.create_task(pool.run_reaper())
    try:
        yield
    finally:
        reaper.cancel()
        with suppress(asyncio.CancelledError):
            await reaper
        await pool.close()


app = FastAPI(title="InnomightLabs Infra CLI Runner", version="0.4.0", lifespan=lifespan)
app.include_router(router)

__all__ = ["app"]
