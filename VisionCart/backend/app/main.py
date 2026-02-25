"""
VisionCart – FastAPI Application Entry Point

Initializes the ASGI server with:
  - REST API routes (auth, orders, sessions, inventory)
  - WebSocket handlers (signaling, overlay, state sync)
  - CORS middleware for cross-origin browser access
  - Lifespan manager for Redis pool and DB connection
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.api.auth import router as auth_router
from app.api.customer_auth import router as customer_auth_router
from app.api.shopper_auth import router as shopper_auth_router
from app.api.orders import router as orders_router
from app.api.sessions import router as sessions_router
from app.api.inventory import router as inventory_router
from app.api.inspect import router as inspect_router
from app.ws.signaling import router as signaling_ws_router
from app.ws.overlay import router as overlay_ws_router
from app.ws.state_sync import router as state_sync_ws_router
from app.ws.video_relay import router as video_relay_ws_router

settings = get_settings()
logger = logging.getLogger("visioncart")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle: create DB tables, Redis pool, logging."""
    logging.basicConfig(level=settings.LOG_LEVEL.upper())
    logger.info("🛒 VisionCart server starting...")

    # Create SQLite tables (no-op if they already exist)
    from app.models.database import engine
    from app.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ SQLite database ready")

    # Seed 10 shoppers if the table is empty
    from app.models import Shopper
    from app.models.database import async_session_factory
    from sqlalchemy import select

    _SHOPPER_NAMES = [
        "Alex M.", "Jordan T.", "Sam R.", "Casey L.", "Morgan P.",
        "Riley B.", "Taylor S.", "Quinn H.", "Drew N.", "Avery K.",
    ]
    async with async_session_factory() as db:
        existing = (await db.execute(select(Shopper))).scalars().all()
        if not existing:
            for name in _SHOPPER_NAMES:
                db.add(Shopper(name=name))
            await db.commit()
            logger.info("✅ 10 shoppers seeded into shoppers_list")

    # Initialize Redis connection pool
    app.state.redis = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=50,
    )
    logger.info("✅ Redis connected")

    yield

    # Cleanup
    await app.state.redis.close()
    logger.info("🛑 VisionCart server stopped")


app = FastAPI(
    title="VisionCart API",
    description="Live, Collaborative, AI-Augmented Grocery Experience",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── REST API Routes ───────────────────────────────────────────────────────────

app.include_router(auth_router, prefix="/api/users", tags=["Users"])
app.include_router(customer_auth_router, prefix="/api/customer", tags=["Customer Auth"])
app.include_router(shopper_auth_router, prefix="/api/shopper", tags=["Shopper"])
app.include_router(orders_router, prefix="/api/orders", tags=["Orders"])
app.include_router(sessions_router, prefix="/api/sessions", tags=["Sessions"])
app.include_router(inventory_router, prefix="/api/inventory", tags=["Inventory"])
app.include_router(inspect_router, prefix="/api", tags=["Quality Inspection"])

# ── WebSocket Routes ──────────────────────────────────────────────────────────

app.include_router(signaling_ws_router, prefix="/ws", tags=["WebSocket - Signaling"])
app.include_router(overlay_ws_router, prefix="/ws", tags=["WebSocket - Overlay"])
app.include_router(state_sync_ws_router, prefix="/ws", tags=["WebSocket - State"])
app.include_router(video_relay_ws_router, prefix="/ws", tags=["WebSocket - Video"])


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": "visioncart-api",
        "version": "0.1.0",
    }
