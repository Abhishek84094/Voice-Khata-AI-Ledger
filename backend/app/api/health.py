"""Health check router."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    env: str
    version: str


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    """Standard health check endpoint."""
    return HealthResponse(
        status="ok",
        env="development",
        version="0.1.0",
    )
