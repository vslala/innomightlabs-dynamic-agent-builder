import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from src.auth import auth_router, middleware
from src.agents.router import router as agent_router
from src.apikeys.router import router as apikeys_router
from src.conversations.router import router as conversation_router
from src.settings.router import router as settings_router
from src.memory.router import router as memory_router
from src.llm.router import router as llm_router
from src.widget import widget_router, WidgetAuthMiddleware
from src.exceptions import register_exception_handlers

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = FastAPI(
    title="Dynamic Agent Builder API",
    description="API for building dynamic agents with long-term memory",
    version="0.1.0",
)

# Register global exception handlers
register_exception_handlers(app)

# Dashboard origins (with credentials)
dashboard_origins = [
    "http://localhost:5173",
    "https://vslala.github.io",
]

# Middleware order matters! Last added = first to run.
# Order of execution: CORSMiddleware -> WidgetAuthMiddleware -> AuthMiddleware -> Route

# Dashboard auth middleware (JWT validation) - added first, runs last
app.add_middleware(middleware.AuthMiddleware)

# Widget auth middleware (API key validation) - runs second
app.add_middleware(WidgetAuthMiddleware)

# CORS middleware - added last, runs FIRST (must handle OPTIONS preflight before auth)
# Note: Widget endpoints allow any origin (validated by WidgetAuthMiddleware against API key's allowed_origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins; widget validates via API key, dashboard via auth
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(auth_router)
app.include_router(router=agent_router)
app.include_router(router=apikeys_router)
app.include_router(router=conversation_router)
app.include_router(router=settings_router)
app.include_router(router=memory_router)
app.include_router(router=llm_router)
app.include_router(router=widget_router)


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/")
def root():
    return {"message": "Dynamic Agent Builder API"}


# Lambda handler
handler = Mangum(app, lifespan="off")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
