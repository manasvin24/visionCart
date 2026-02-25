"""
VisionCart – Inventory API
Product catalog search and retrieval.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Inventory
from app.models.database import get_db
from app.schemas import InventoryItem

router = APIRouter()


@router.get("/", response_model=List[InventoryItem])
async def list_inventory(
    category: Optional[str] = None,
    search: Optional[str] = None,
    in_stock: Optional[bool] = True,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Search and list inventory items with optional filters."""
    query = select(Inventory)

    if category:
        query = query.where(Inventory.category == category)
    if in_stock is not None:
        query = query.where(Inventory.in_stock == in_stock)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(
                Inventory.name.ilike(pattern),
                Inventory.brand.ilike(pattern),
                Inventory.sku.ilike(pattern),
            )
        )

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{item_id}", response_model=InventoryItem)
async def get_inventory_item(
    item_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """Get a single inventory item by ID."""
    result = await db.execute(select(Inventory).where(Inventory.id == str(item_id)))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item
