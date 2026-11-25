"""FastAPI application entry point."""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, ORJSONResponse

from app.api.health import router as health_router
from app.api.ledger_api import router as ledger_router
from app.api.ws_voice import router as ws_voice_router
from app.core.config import get_settings
from app.storage.db import get_engine, init_tables, reset_db_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await reset_db_engine()
    engine = get_engine()
    await init_tables(engine)
    yield
    await reset_db_engine()


def create_app() -> FastAPI:
    _settings = get_settings()
    app = FastAPI(
        title="Voice Khata API",
        version="0.1.0",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    app.include_router(health_router)
    app.include_router(ledger_router)
    app.include_router(ws_voice_router)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        frontend_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "frontend", "index.html"
        )
        if os.path.exists(frontend_path):
            with open(frontend_path, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
        return HTMLResponse(content="<h1>Voice Khata API</h1>")

    return app


app = create_app()
