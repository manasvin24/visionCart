"""
VisionCart – Orders API
CRUD for shopping orders with budget tracking.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Order, OrderItem, OrderStatus, OrderItemStatus, Inventory
from app.models.database import get_db
from app.schemas import OrderCreate, OrderResponse, OrderItemResponse

router = APIRouter()


@router.post("/", response_model=OrderResponse, status_code=201)
async def create_order(body: OrderCreate, db: AsyncSession = Depends(get_db)):
    """Create a new shopping order with a budget limit and item list."""
    # MVP: generate a placeholder customer_id (production: pass as query/body param)
    customer_id = str(uuid.uuid4())

    order = Order(
        customer_id=customer_id,
        budget_limit=body.budget_limit,
        currency=body.currency,
        delivery_address=body.delivery_address,
        notes=body.notes,
        status=OrderStatus.DRAFT,
    )
    db.add(order)
    await db.flush()

    # Add items
    for item_req in body.items:
        # Look up inventory for price
        inv_result = await db.execute(
            select(Inventory).where(Inventory.id == str(item_req.inventory_id))
        )
        inv = inv_result.scalar_one_or_none()
        if not inv:
            raise HTTPException(
                status_code=404,
                detail=f"Inventory item {item_req.inventory_id} not found",
            )
        order_item = OrderItem(
            order_id=order.id,
            inventory_id=str(item_req.inventory_id),
            quantity_requested=item_req.quantity_requested,
            unit_price=inv.price,
            status=OrderItemStatus.PENDING,
        )
        db.add(order_item)

    await db.flush()
    await db.refresh(order)

    # Reload with items
    result = await db.execute(
        select(Order)
        .where(Order.id == order.id)
        .options(selectinload(Order.items))
    )
    return result.scalar_one()


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(order_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get order details including all items and current total."""
    result = await db.execute(
        select(Order)
        .where(Order.id == str(order_id))
        .options(selectinload(Order.items))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.post("/{order_id}/items/{item_id}/pick", response_model=OrderItemResponse)
async def pick_item(
    order_id: uuid.UUID,
    item_id: int,
    freshness_score: float = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Mark an item as picked. Updates the cart total.
    Called by the shopper when physically picking up an item.
    """
    result = await db.execute(
        select(OrderItem).where(
            OrderItem.id == item_id,
            OrderItem.order_id == str(order_id),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Order item not found")

    item.status = OrderItemStatus.PICKED
    item.quantity_picked = item.quantity_requested
    item.freshness_score = freshness_score
    from datetime import datetime, timezone
    item.picked_at = datetime.now(timezone.utc)

    # Update order total
    order_result = await db.execute(
        select(Order).where(Order.id == str(order_id))
    )
    order = order_result.scalar_one()
    order.current_total += item.unit_price * item.quantity_picked

    await db.flush()
    await db.refresh(item)
    return item
