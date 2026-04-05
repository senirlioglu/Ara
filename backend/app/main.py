"""Mapping Engine — FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .routers import weeks, pages, mappings, products

app = FastAPI(title="Mapping Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static file serving for rendered page images
settings.weeks_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/weeks", StaticFiles(directory=str(settings.weeks_dir)), name="weeks_static")

# Routers
app.include_router(weeks.router,    prefix="/weeks",    tags=["weeks"])
app.include_router(pages.router,    prefix="/weeks",    tags=["pages"])
app.include_router(mappings.router, prefix="/weeks",    tags=["mappings"])
app.include_router(products.router, prefix="/weeks",    tags=["products"])


@app.get("/health")
async def health():
    return {"status": "ok"}
