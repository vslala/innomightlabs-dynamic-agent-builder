from fastapi import FastAPI

from src.infra_cli_runner.router import router


app = FastAPI(title="InnomightLabs Infra CLI Runner", version="0.2.0")
app.include_router(router)

__all__ = ["app"]
