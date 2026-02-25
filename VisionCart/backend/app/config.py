"""
VisionCart – Application Configuration
Loads environment variables with sensible defaults for local development.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration sourced from environment / .env file."""

    # ── Server ────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    LOG_LEVEL: str = "info"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8081"

    # ── Database ──────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./visioncart.db"
    DATABASE_URL_SYNC: str = "sqlite:///./visioncart.db"

    # ── Redis ─────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── WebRTC / TURN ─────────────────────────────────────────────────────
    STUN_SERVER: str = "stun:stun.l.google.com:19302"
    TURN_SERVER_URL: str = ""
    TURN_SERVER_USERNAME: str = ""
    TURN_SERVER_CREDENTIAL: str = ""

    # ── AI / CV ───────────────────────────────────────────────────────────
    AI_MODEL_PATH: str = "./ai-engine/models/"
    FRESHNESS_THRESHOLD: float = 0.65

    # ── Grok Vision API ──────────────────────────────────────────────────
    XAI_API_KEY: str = ""
    GROK_VISION_MODEL: str = "grok-2-vision-1212"

    # ── Whisper ───────────────────────────────────────────────────────────
    WHISPER_API_KEY: str = ""
    WHISPER_MODEL: str = "base"

    # ── Budget ────────────────────────────────────────────────────────────
    MAX_BUDGET_ALERT_PERCENT: int = 90
    DEFAULT_CURRENCY: str = "USD"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def ice_servers(self) -> List[dict]:
        servers = [{"urls": self.STUN_SERVER}]
        if self.TURN_SERVER_URL:
            servers.append(
                {
                    "urls": self.TURN_SERVER_URL,
                    "username": self.TURN_SERVER_USERNAME,
                    "credential": self.TURN_SERVER_CREDENTIAL,
                }
            )
        return servers

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
