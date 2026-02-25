"""
VisionCart – SQLAlchemy ORM Models
Maps to the schema defined in docs/SCHEMA.md
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ── Enums ─────────────────────────────────────────────────────────────────────

import enum


class UserRole(str, enum.Enum):
    SHOPPER = "shopper"
    CUSTOMER = "customer"


class SessionStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OrderStatus(str, enum.Enum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OrderItemStatus(str, enum.Enum):
    PENDING = "pending"
    FOUND = "found"
    PICKED = "picked"
    NOT_FOUND = "not_found"
    SUBSTITUTED = "substituted"


class SubstitutionStatus(str, enum.Enum):
    SUGGESTED = "suggested"
    APPROVED = "approved"
    REJECTED = "rejected"


class SessionEventType(str, enum.Enum):
    TAP = "tap"
    VOICE = "voice"
    AI_DETECTION = "ai_detection"
    ITEM_PICK = "item_pick"
    ITEM_RETURN = "item_return"
    FRESHNESS_ALERT = "freshness_alert"
    BUDGET_ALERT = "budget_alert"


# ── Models ────────────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    preferences: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    customer_sessions = relationship(
        "Session", foreign_keys="Session.customer_id", back_populates="customer"
    )
    shopper_sessions = relationship(
        "Session", foreign_keys="Session.shopper_id", back_populates="shopper"
    )
    orders = relationship("Order", back_populates="customer")
    budget_alerts = relationship("BudgetAlert", back_populates="user")


class Customer(Base):
    """Customer accounts for login/signup (customers_list table)."""
    __tablename__ = "customers_list"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)  # hashed
    address_line_1: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address_line_2: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    zip_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Shopper(Base):
    """Pre-seeded shopper accounts (shoppers_list table)."""
    __tablename__ = "shoppers_list"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    shopper_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        String(36), ForeignKey("orders.id"), nullable=True
    )
    status: Mapped[SessionStatus] = mapped_column(
        SAEnum(SessionStatus), default=SessionStatus.PENDING
    )
    signaling_room: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False
    )
    ice_servers: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    quality_metrics: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    customer = relationship(
        "User", foreign_keys=[customer_id], back_populates="customer_sessions"
    )
    shopper = relationship(
        "User", foreign_keys=[shopper_id], back_populates="shopper_sessions"
    )
    order = relationship("Order", back_populates="session")
    events = relationship(
        "SessionEvent", back_populates="session", order_by="SessionEvent.created_at"
    )

    __table_args__ = (
        Index("idx_sessions_status", "status"),
        Index("idx_sessions_customer", "customer_id"),
        Index("idx_sessions_shopper", "shopper_id"),
    )


class SessionEvent(Base):
    __tablename__ = "session_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        String(36), ForeignKey("sessions.id"), nullable=False
    )
    event_type: Mapped[SessionEventType] = mapped_column(
        SAEnum(SessionEventType), nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    timestamp_offset_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    session = relationship("Session", back_populates="events")

    __table_args__ = (
        Index("idx_session_events_session", "session_id", "created_at"),
        Index("idx_session_events_type", "session_id", "event_type"),
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus), default=OrderStatus.DRAFT
    )
    budget_limit: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("100.00")
    )
    current_total: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00")
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    delivery_address: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    customer = relationship("User", back_populates="orders")
    session = relationship("Session", back_populates="order", uselist=False)
    items = relationship("OrderItem", back_populates="order")
    substitutions = relationship("Substitution", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[uuid.UUID] = mapped_column(
        String(36), ForeignKey("orders.id"), nullable=False
    )
    inventory_id: Mapped[uuid.UUID] = mapped_column(
        String(36), ForeignKey("inventory.id"), nullable=False
    )
    quantity_requested: Mapped[int] = mapped_column(Integer, default=1)
    quantity_picked: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[OrderItemStatus] = mapped_column(
        SAEnum(OrderItemStatus), default=OrderItemStatus.PENDING
    )
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    freshness_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    picked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    order = relationship("Order", back_populates="items")
    inventory = relationship("Inventory", back_populates="order_items")

    __table_args__ = (
        Index("idx_order_items_order", "order_id"),
        Index("idx_order_items_status", "order_id", "status"),
    )


class Inventory(Base):
    __tablename__ = "inventory"

    id: Mapped[uuid.UUID] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    sku: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    brand: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), default="each")
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    nutrition_info: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    detection_labels: Mapped[Optional[dict]] = mapped_column(JSON, default=list)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    order_items = relationship("OrderItem", back_populates="inventory")

    __table_args__ = (
        Index("idx_inventory_category", "category"),
    )


class Substitution(Base):
    __tablename__ = "substitutions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[uuid.UUID] = mapped_column(
        String(36), ForeignKey("orders.id"), nullable=False
    )
    original_item_id: Mapped[uuid.UUID] = mapped_column(
        String(36), ForeignKey("inventory.id"), nullable=False
    )
    replacement_item_id: Mapped[uuid.UUID] = mapped_column(
        String(36), ForeignKey("inventory.id"), nullable=False
    )
    status: Mapped[SubstitutionStatus] = mapped_column(
        SAEnum(SubstitutionStatus), default=SubstitutionStatus.SUGGESTED
    )
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    price_difference: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    order = relationship("Order", back_populates="substitutions")
    original_item = relationship("Inventory", foreign_keys=[original_item_id])
    replacement_item = relationship("Inventory", foreign_keys=[replacement_item_id])


class BudgetAlert(Base):
    __tablename__ = "budget_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[uuid.UUID] = mapped_column(
        String(36), ForeignKey("orders.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    threshold_percent: Mapped[float] = mapped_column(Float, nullable=False)
    current_percent: Mapped[float] = mapped_column(Float, nullable=False)
    cart_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    budget_limit: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user = relationship("User", back_populates="budget_alerts")
