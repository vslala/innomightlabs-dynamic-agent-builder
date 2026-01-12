from fastapi import FastAPI
from mangum import Mangum

from src.auth import auth_router

app = FastAPI(
    title="Dynamic Agent Builder API",
    description="API for building dynamic agents with long-term memory",
    version="0.1.0",
)

app.include_router(auth_router)


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
