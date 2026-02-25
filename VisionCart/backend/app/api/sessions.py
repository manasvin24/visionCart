"""
VisionCart – Sessions API
Create, join, and manage live shopping sessions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Session, SessionStatus
from app.models.database import get_db
from app.schemas import SessionCreate, SessionResponse

router = APIRouter()
settings = get_settings()


@router.post("/", response_model=SessionResponse, status_code=201)
async def create_session(body: SessionCreate, db: AsyncSession = Depends(get_db)):
    """
    Create a new live shopping session.
    The customer initiates a session; a shopper joins later.
    """
    # MVP: generate a placeholder customer_id (production: pass as query/body param)
    customer_id = str(uuid.uuid4())

    signaling_room = f"vc-{uuid.uuid4().hex[:12]}"

    session = Session(
        customer_id=customer_id,
        order_id=str(body.order_id) if body.order_id else None,
        status=SessionStatus.PENDING,
        signaling_room=signaling_room,
        ice_servers=settings.ice_servers,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return session


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get session details including ICE server configuration."""
    result = await db.execute(
        select(Session).where(Session.id == str(session_id))
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/{session_id}/join", response_model=SessionResponse)
async def join_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Shopper joins an existing session.
    Transitions status from PENDING → ACTIVE.
    """
    result = await db.execute(
        select(Session).where(Session.id == str(session_id))
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status != SessionStatus.PENDING:
        raise HTTPException(status_code=409, detail="Session not in pending state")

    # MVP: generate a placeholder shopper_id (production: pass as query/body param)
    session.shopper_id = str(uuid.uuid4())
    session.status = SessionStatus.ACTIVE
    session.started_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(session)
    return session


@router.post("/{session_id}/end", response_model=SessionResponse)
async def end_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """End a live session."""
    result = await db.execute(
        select(Session).where(Session.id == str(session_id))
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.status = SessionStatus.COMPLETED
    session.ended_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(session)
    return session
