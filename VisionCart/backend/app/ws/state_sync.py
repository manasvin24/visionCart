"""
VisionCart – State Synchronization WebSocket Handler

Real-time cart state, budget tracking, and shopping list synchronization
between Shopper and Customer. Uses Redis PubSub for horizontal scaling.

State channels:
  - cart:{session_id}     → Item additions/removals, quantities, totals
  - budget:{session_id}   → Budget alerts and threshold notifications
  - list:{session_id}     → Shopping list status (pending/found/picked)
  - ai:{session_id}       → AI detection events and freshness scores
"""

from __future__ import annotations

import json
import logging
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

router = APIRouter()
logger = logging.getLogger("visioncart.state_sync")


# ── In-Memory State Store (Redis-backed in production) ────────────────────────


@dataclass
class CartItem:
    """Single item in the live cart."""
    item_id: str
    inventory_id: str
    name: str
    quantity_requested: int
    quantity_picked: int = 0
    unit_price: float = 0.0
    status: str = "pending"  # pending | found | picked | not_found | substituted
    freshness_score: Optional[float] = None
    freshness_details: Optional[Dict] = None


@dataclass
class CartState:
    """Complete state of a shopping session cart."""
    session_id: str
    order_id: str
    items: Dict[str, CartItem] = field(default_factory=dict)
    budget_limit: float = 100.0
    currency: str = "USD"
    last_updated: float = 0.0

    @property
    def current_total(self) -> float:
        return sum(
            item.unit_price * item.quantity_picked
            for item in self.items.values()
            if item.status == "picked"
        )

    @property
    def budget_percent(self) -> float:
        if self.budget_limit <= 0:
            return 0.0
        return (self.current_total / self.budget_limit) * 100.0

    @property
    def items_pending(self) -> int:
        return sum(1 for i in self.items.values() if i.status == "pending")

    @property
    def items_picked(self) -> int:
        return sum(1 for i in self.items.values() if i.status == "picked")

    def to_sync_payload(self) -> Dict[str, Any]:
        """Serialize to a WebSocket broadcast payload."""
        return {
            "type": "cart_state",
            "session_id": self.session_id,
            "order_id": self.order_id,
            "items": [asdict(item) for item in self.items.values()],
            "current_total": round(self.current_total, 2),
            "budget_limit": self.budget_limit,
            "budget_percent": round(self.budget_percent, 1),
            "currency": self.currency,
            "items_pending": self.items_pending,
            "items_picked": self.items_picked,
            "items_total": len(self.items),
            "last_updated": self.last_updated,
        }


class BudgetEngine:
    """
    Monitors cart total against budget limit and generates alerts.
    Supports configurable thresholds and cooldown to avoid alert spam.
    """

    def __init__(self, alert_threshold_percent: float = 90.0, cooldown_sec: float = 30.0):
        self.alert_threshold = alert_threshold_percent
        self.cooldown_sec = cooldown_sec
        self._last_alert_time: Dict[str, float] = {}

    def check(self, cart: CartState) -> Optional[Dict[str, Any]]:
        """
        Evaluate budget status. Returns an alert dict if threshold is exceeded.
        """
        percent = cart.budget_percent
        session_id = cart.session_id

        if percent < self.alert_threshold:
            return None

        # Cooldown check
        now = time.time()
        last = self._last_alert_time.get(session_id, 0)
        if now - last < self.cooldown_sec:
            return None

        self._last_alert_time[session_id] = now

        severity = "warning" if percent < 100 else "critical"
        remaining = max(0, cart.budget_limit - cart.current_total)

        return {
            "type": "budget_alert",
            "severity": severity,
            "budget_percent": round(percent, 1),
            "current_total": round(cart.current_total, 2),
            "budget_limit": cart.budget_limit,
            "remaining": round(remaining, 2),
            "currency": cart.currency,
            "message": (
                f"⚠️ Budget {severity}: {percent:.0f}% used "
                f"(${cart.current_total:.2f} / ${cart.budget_limit:.2f}). "
                f"${remaining:.2f} remaining."
            ),
            "timestamp": now,
        }


class SubstitutionEngine:
    """
    Suggests item substitutions when items are not found or fail freshness checks.
    In production, this queries the Inventory table for alternatives.
    """

    def suggest(
        self,
        item: CartItem,
        reason: str,
        alternatives: List[Dict] = None,
    ) -> Dict[str, Any]:
        """Generate a substitution suggestion."""
        return {
            "type": "substitution_suggestion",
            "original_item": asdict(item),
            "reason": reason,
            "alternatives": alternatives or [],
            "timestamp": time.time(),
        }


# ── Session State Registry ────────────────────────────────────────────────────

_cart_states: Dict[str, CartState] = {}
_session_connections: Dict[str, Dict[str, WebSocket]] = {}
_budget_engine = BudgetEngine()
_substitution_engine = SubstitutionEngine()


async def broadcast_to_session(session_id: str, message: Dict) -> None:
    """Send a message to all connected peers in a session."""
    connections = _session_connections.get(session_id, {})
    for role, ws in list(connections.items()):
        try:
            await ws.send_json(message)
        except Exception as e:
            logger.warning(f"Failed to send to {role} in {session_id}: {e}")


# ── WebSocket Endpoint ────────────────────────────────────────────────────────


@router.websocket("/state/{session_id}")
async def state_sync_endpoint(
    websocket: WebSocket,
    session_id: str,
    role: str = Query(..., pattern="^(shopper|customer)$"),
):
    """
    Real-time state synchronization channel.

    Messages from either peer:
      → { "type": "init_cart", "order_id": "...", "items": [...], "budget_limit": 100 }
      → { "type": "item_picked", "item_id": "...", "freshness_score": 0.85 }
      → { "type": "item_returned", "item_id": "..." }
      → { "type": "item_not_found", "item_id": "..." }
      → { "type": "approve_substitution", "item_id": "...", "replacement_id": "..." }
      → { "type": "request_state" }

    Broadcast to all:
      ← { "type": "cart_state", ... }   (full state sync)
      ← { "type": "budget_alert", ... } (when threshold exceeded)
      ← { "type": "substitution_suggestion", ... }
    """
    await websocket.accept()

    if session_id not in _session_connections:
        _session_connections[session_id] = {}
    _session_connections[session_id][role] = websocket

    try:
        # Send current state if exists
        if session_id in _cart_states:
            await websocket.send_json(_cart_states[session_id].to_sync_payload())

        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = message.get("type")

            # ── Initialize cart from order ──
            if msg_type == "init_cart":
                cart = CartState(
                    session_id=session_id,
                    order_id=message.get("order_id", ""),
                    budget_limit=float(message.get("budget_limit", 100)),
                    currency=message.get("currency", "USD"),
                    last_updated=time.time(),
                )
                for item_data in message.get("items", []):
                    cart.items[item_data["item_id"]] = CartItem(
                        item_id=item_data["item_id"],
                        inventory_id=item_data.get("inventory_id", ""),
                        name=item_data.get("name", "Unknown"),
                        quantity_requested=item_data.get("quantity_requested", 1),
                        unit_price=float(item_data.get("unit_price", 0)),
                    )
                _cart_states[session_id] = cart
                await broadcast_to_session(session_id, cart.to_sync_payload())
                continue

            # ── Item picked by shopper ──
            if msg_type == "item_picked":
                cart = _cart_states.get(session_id)
                if not cart:
                    continue
                item_id = message.get("item_id")
                item = cart.items.get(item_id)
                if not item:
                    continue

                item.status = "picked"
                item.quantity_picked = item.quantity_requested
                item.freshness_score = message.get("freshness_score")
                item.freshness_details = message.get("freshness_details")
                cart.last_updated = time.time()

                # Check freshness threshold
                from app.config import get_settings
                settings = get_settings()
                if (
                    item.freshness_score is not None
                    and item.freshness_score < settings.FRESHNESS_THRESHOLD
                ):
                    suggestion = _substitution_engine.suggest(
                        item,
                        reason=f"Low freshness score: {item.freshness_score:.2f}",
                    )
                    await broadcast_to_session(session_id, suggestion)

                # Broadcast updated state
                await broadcast_to_session(session_id, cart.to_sync_payload())

                # Check budget
                alert = _budget_engine.check(cart)
                if alert:
                    await broadcast_to_session(session_id, alert)
                continue

            # ── Item returned ──
            if msg_type == "item_returned":
                cart = _cart_states.get(session_id)
                if not cart:
                    continue
                item_id = message.get("item_id")
                item = cart.items.get(item_id)
                if not item:
                    continue

                item.status = "pending"
                item.quantity_picked = 0
                item.freshness_score = None
                cart.last_updated = time.time()
                await broadcast_to_session(session_id, cart.to_sync_payload())
                continue

            # ── Item not found ──
            if msg_type == "item_not_found":
                cart = _cart_states.get(session_id)
                if not cart:
                    continue
                item_id = message.get("item_id")
                item = cart.items.get(item_id)
                if not item:
                    continue

                item.status = "not_found"
                cart.last_updated = time.time()
                suggestion = _substitution_engine.suggest(
                    item, reason="Item not found in store"
                )
                await broadcast_to_session(session_id, cart.to_sync_payload())
                await broadcast_to_session(session_id, suggestion)
                continue

            # ── Voice prompt from customer → relay to shopper (text or audio) ──
            if msg_type == "voice_prompt":
                prompt_msg: Dict[str, Any] = {
                    "type": "voice_prompt",
                    "from": role,
                    "timestamp": time.time(),
                }
                # Forward text and/or audio fields
                if message.get("text"):
                    prompt_msg["text"] = message["text"]
                if message.get("audio"):
                    prompt_msg["audio"] = message["audio"]
                    prompt_msg["mime"] = message.get("mime", "audio/webm")

                # Send to all OTHER peers (not back to sender)
                connections = _session_connections.get(session_id, {})
                for peer_role, peer_ws in list(connections.items()):
                    if peer_role != role:
                        try:
                            await peer_ws.send_text(json.dumps(prompt_msg))
                            logger.info(f"[{session_id}] voice_prompt relayed to {peer_role}")
                        except Exception as e:
                            logger.warning(f"[{session_id}] Failed to relay voice_prompt to {peer_role}: {e}")
                continue

            # ── Add item to cart (from customer) ──
            if msg_type == "add_item":
                cart = _cart_states.get(session_id)
                if not cart:
                    continue
                item_id = message.get("item_id", f"item-{int(time.time()*1000)}")
                cart.items[item_id] = CartItem(
                    item_id=item_id,
                    inventory_id=message.get("inventory_id", ""),
                    name=message.get("name", "New Item"),
                    quantity_requested=int(message.get("quantity_requested", 1)),
                    unit_price=float(message.get("unit_price", 0)),
                )
                cart.last_updated = time.time()
                await broadcast_to_session(session_id, cart.to_sync_payload())
                logger.info(f"[{session_id}] add_item: {item_id} ({message.get('name')})")
                continue

            # ── Remove item from cart (from customer) ──
            if msg_type == "remove_item":
                cart = _cart_states.get(session_id)
                if not cart:
                    continue
                item_id = message.get("item_id")
                if item_id and item_id in cart.items:
                    del cart.items[item_id]
                    cart.last_updated = time.time()
                    await broadcast_to_session(session_id, cart.to_sync_payload())
                    logger.info(f"[{session_id}] remove_item: {item_id}")
                continue

            # ── Request full state ──
            if msg_type == "request_state":
                cart = _cart_states.get(session_id)
                if cart:
                    await websocket.send_json(cart.to_sync_payload())
                continue

    except WebSocketDisconnect:
        logger.info(f"[{session_id}] {role} disconnected from state sync")
    finally:
        if session_id in _session_connections:
            _session_connections[session_id].pop(role, None)
            if not _session_connections[session_id]:
                del _session_connections[session_id]
