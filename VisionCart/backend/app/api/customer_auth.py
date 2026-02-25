"""
VisionCart – Customer Authentication API
Signup and login endpoints for customers_list table.
"""

from __future__ import annotations

import hashlib
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Customer
from app.models.database import get_db
from app.schemas import CustomerSignup, CustomerLogin, CustomerResponse, LoginResponse

router = APIRouter()
logger = logging.getLogger("visioncart.customer_auth")


def hash_password(password: str) -> str:
    """Simple SHA-256 hash for password storage."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against stored hash."""
    return hash_password(password) == hashed


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/signup", response_model=LoginResponse, status_code=201)
async def signup(body: CustomerSignup, db: AsyncSession = Depends(get_db)):
    """Register a new customer account."""
    # Check if username already exists
    existing = await db.execute(
        select(Customer).where(Customer.username == body.username)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already taken")

    # Create new customer
    customer = Customer(
        username=body.username,
        password=hash_password(body.password),
        address_line_1=body.address_line_1,
        address_line_2=body.address_line_2,
        state=body.state,
        zip_code=body.zip_code,
    )
    db.add(customer)
    await db.flush()
    await db.refresh(customer)

    logger.info(f"New customer signed up: {body.username}")

    return LoginResponse(
        success=True,
        message="Account created successfully",
        customer=CustomerResponse.model_validate(customer),
    )


@router.post("/login", response_model=LoginResponse)
async def login(body: CustomerLogin, db: AsyncSession = Depends(get_db)):
    """Login with username and password."""
    result = await db.execute(
        select(Customer).where(Customer.username == body.username)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if not verify_password(body.password, customer.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    logger.info(f"Customer logged in: {body.username}")

    return LoginResponse(
        success=True,
        message="Login successful",
        customer=CustomerResponse.model_validate(customer),
    )


@router.get("/me/{customer_id}", response_model=CustomerResponse)
async def get_customer(customer_id: int, db: AsyncSession = Depends(get_db)):
    """Get customer profile by ID."""
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    return CustomerResponse.model_validate(customer)
