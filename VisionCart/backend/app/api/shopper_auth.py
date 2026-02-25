"""
VisionCart – Shopper API
Provides a read-only list of the 10 pre-seeded shoppers from shoppers_list.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Shopper
from app.models.database import get_db

router = APIRouter()


class ShopperOut(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


@router.get("/list", response_model=List[ShopperOut])
async def list_shoppers(db: AsyncSession = Depends(get_db)):
    """Return all shoppers in the shoppers_list table."""
    result = await db.execute(select(Shopper).order_by(Shopper.id))
    shoppers = result.scalars().all()
    return shoppers
