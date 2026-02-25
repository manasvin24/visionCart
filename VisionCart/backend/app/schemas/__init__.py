"""
VisionCart – Pydantic Schemas for Request/Response Validation
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field


# ── Auth ──────────────────────────────────────────────────────────────────────


class UserCreate(BaseModel):
    email: EmailStr
    role: str = Field(pattern="^(shopper|customer)$")
    display_name: str = Field(min_length=1, max_length=100)
    phone: Optional[str] = None


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    display_name: str
    phone: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ── Session ───────────────────────────────────────────────────────────────────


class SessionCreate(BaseModel):
    order_id: Optional[uuid.UUID] = None


class SessionResponse(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    shopper_id: Optional[uuid.UUID]
    order_id: Optional[uuid.UUID]
    status: str
    signaling_room: str
    ice_servers: List[Dict[str, Any]]
    created_at: datetime
    started_at: Optional[datetime]

    class Config:
        from_attributes = True


class SessionJoin(BaseModel):
    session_id: uuid.UUID


# ── Order ─────────────────────────────────────────────────────────────────────


class OrderCreate(BaseModel):
    budget_limit: Decimal = Field(ge=0, default=Decimal("100.00"))
    currency: str = Field(default="USD", max_length=3)
    delivery_address: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    items: List["OrderItemCreate"] = []


class OrderItemCreate(BaseModel):
    inventory_id: uuid.UUID
    quantity_requested: int = Field(ge=1, default=1)


class OrderItemResponse(BaseModel):
    id: int
    inventory_id: uuid.UUID
    inventory_name: Optional[str] = None
    quantity_requested: int
    quantity_picked: int
    status: str
    unit_price: Decimal
    freshness_score: Optional[float]
    picked_at: Optional[datetime]

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    status: str
    budget_limit: Decimal
    current_total: Decimal
    currency: str


# ── Customer Auth ─────────────────────────────────────────────────────────────


class CustomerSignup(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=6, max_length=100)
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None


class CustomerLogin(BaseModel):
    username: str
    password: str


class CustomerResponse(BaseModel):
    id: int
    username: str
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        extra = 'ignore'


class LoginResponse(BaseModel):
    success: bool
    message: str
    customer: Optional[CustomerResponse] = None


# ── Inventory ─────────────────────────────────────────────────────────────────


class InventoryItem(BaseModel):
    id: uuid.UUID
    sku: str
    name: str
    category: str
    brand: Optional[str]
    price: Decimal
    unit: str
    image_url: Optional[str]
    in_stock: bool

    class Config:
        from_attributes = True


# ── WebSocket Messages ────────────────────────────────────────────────────────


class WSMessage(BaseModel):
    """Base WebSocket message envelope."""
    type: str
    payload: Dict[str, Any] = {}
    timestamp: Optional[float] = None


class SignalingMessage(BaseModel):
    """WebRTC signaling message (SDP offer/answer, ICE candidate)."""
    type: str = Field(pattern="^(offer|answer|ice-candidate|bye)$")
    sdp: Optional[str] = None
    candidate: Optional[Dict[str, Any]] = None


class TapEvent(BaseModel):
    """Customer tap-to-highlight event."""
    x: float = Field(ge=0.0, le=1.0, description="Normalized X [0,1]")
    y: float = Field(ge=0.0, le=1.0, description="Normalized Y [0,1]")
    radius: float = Field(default=30.0, ge=5.0, le=100.0)
    color: str = Field(default="#FF6B35")
    duration_ms: int = Field(default=3000, ge=500, le=10000)


class VoiceChunk(BaseModel):
    """Audio chunk for Whisper transcription."""
    audio_b64: str
    sample_rate: int = 16000
    encoding: str = "pcm_f32le"


class AIDetection(BaseModel):
    """AI detection result for a single object."""
    label: str
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: List[float] = Field(description="[x, y, width, height] normalized")
    freshness_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    freshness_details: Optional[Dict[str, float]] = None


class CartUpdate(BaseModel):
    """Real-time cart state update."""
    order_id: uuid.UUID
    items: List[OrderItemResponse]
    current_total: Decimal
    budget_limit: Decimal
    budget_percent: float
    alert: Optional[str] = None


class SubstitutionRequest(BaseModel):
    order_id: uuid.UUID
    original_item_id: uuid.UUID
    replacement_item_id: uuid.UUID
    reason: str
