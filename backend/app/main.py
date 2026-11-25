"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from app.api.health import router as health_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    _settings = get_settings()
    app = FastAPI(
        title="Voice Khata API",
        version="0.1.0",
        default_response_class=ORJSONResponse,
    )

    app.include_router(health_router)
    return app


app = create_app()
