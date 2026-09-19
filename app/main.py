"""FastAPI application. Tables are created on startup, more routers land in later phases."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from app.api.recordings import router as recordings_router
from app.config import get_settings
from app.db import create_all


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    create_all()
    yield


app = FastAPI(
    title="Salegate",
    description="QA gate for sales calls. No sale ships unscored.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(recordings_router)


class Health(BaseModel):
    status: str
    llm_enabled: bool
    qa_sample_percent: int


@app.get("/health", response_model=Health)
def health() -> Health:
    """Liveness plus the two settings worth seeing. No secrets are returned."""
    settings = get_settings()
    return Health(
        status="ok",
        llm_enabled=settings.llm_enabled,
        qa_sample_percent=settings.qa_sample_percent,
    )
