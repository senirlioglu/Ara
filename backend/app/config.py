"""Application configuration — loaded from environment."""

from __future__ import annotations

import os
from pathlib import Path


def _require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"{name} environment variable is required")
    return val


class Settings:
    # --- Database ---
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/mapping_engine",
    )
    # Sync URL for migrations / worker (no asyncpg)
    DATABASE_URL_SYNC: str = os.getenv(
        "DATABASE_URL_SYNC",
        "postgresql://postgres:postgres@localhost:5432/mapping_engine",
    )

    # --- Redis ---
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # --- Storage ---
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", "/data"))

    # --- Auth ---
    # API_KEY zorunlu: dev için .env'de ayarla, prod'da Railway/Streamlit secrets
    API_KEY: str = _require_env("API_KEY")

    # --- Render ---
    RENDER_ZOOM: float = float(os.getenv("RENDER_ZOOM", "2.0"))
    JPEG_QUALITY: int = int(os.getenv("JPEG_QUALITY", "80"))

    # --- Derived ---
    @property
    def weeks_dir(self) -> Path:
        return self.DATA_DIR / "weeks"


settings = Settings()
