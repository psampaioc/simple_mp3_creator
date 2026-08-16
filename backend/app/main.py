from fastapi import FastAPI

from app.settings import settings

app = FastAPI(title="Simple MP3 Creator API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.app_env}

