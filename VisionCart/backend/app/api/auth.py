"""
VisionCart – Users API
Simple user management (no authentication).
"""

from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserRole
from app.models.database import get_db
from app.schemas import UserCreate, UserResponse

router = APIRouter()


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(body: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new user (shopper or customer)."""
    # Check for existing email
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=body.email,
        role=UserRole(body.role),
        display_name=body.display_name,
        phone=body.phone,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    role: str = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """List users, optionally filtered by role."""
    query = select(User)
    if role:
        query = query.where(User.role == UserRole(role))
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get a single user by ID."""
    result = await db.execute(select(User).where(User.id == str(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
