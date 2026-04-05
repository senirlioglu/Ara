"""Simple API-key authentication."""

from __future__ import annotations

from fastapi import Header, HTTPException

from .config import settings


async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
