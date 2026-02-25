"""
VisionCart – WebRTC Signaling WebSocket Handler

Manages SDP offer/answer exchange and ICE candidate trickle between
the Shopper and Customer for establishing a peer-to-peer WebRTC connection.

Protocol:
  1. Both peers connect to ws://<host>/ws/signaling/<room_id>?role=<shopper|customer>
  2. Shopper sends { type: "offer", sdp: "..." }
  3. Server forwards to Customer
  4. Customer sends { type: "answer", sdp: "..." }
  5. Server forwards to Shopper
  6. Both sides trickle ICE candidates: { type: "ice-candidate", candidate: {...} }
  7. Either side can send { type: "bye" } to cleanly terminate

Design: Uses Redis PubSub for horizontal scaling across multiple server instances.
"""

from __future__ import annotations

import json
import logging
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

router = APIRouter()
logger = logging.getLogger("visioncart.signaling")

# ── In-Memory Room Registry (single-instance; Redis PubSub for multi-instance) ─

RoomConnections = Dict[str, Dict[str, WebSocket]]  # room_id -> {role -> ws}
rooms: RoomConnections = {}


class SignalingRoom:
    """
    Manages a signaling room with exactly two peers: 'shopper' and 'customer'.
    Thread-safe via asyncio single-threaded event loop.
    """

    def __init__(self, room_id: str):
        self.room_id = room_id
        self.peers: Dict[str, WebSocket] = {}  # role -> WebSocket

    def add_peer(self, role: str, ws: WebSocket) -> None:
        if role in self.peers:
            raise ValueError(f"Role '{role}' already connected in room {self.room_id}")
        self.peers[role] = ws
        logger.info(f"[{self.room_id}] {role} joined (total: {len(self.peers)})")

    def remove_peer(self, role: str) -> None:
        self.peers.pop(role, None)
        logger.info(f"[{self.room_id}] {role} left (total: {len(self.peers)})")

    def get_other_peer(self, sender_role: str) -> WebSocket | None:
        """Get the WebSocket of the other peer in the room."""
        for role, ws in self.peers.items():
            if role != sender_role:
                return ws
        return None

    @property
    def is_empty(self) -> bool:
        return len(self.peers) == 0


# Global room registry
_rooms: Dict[str, SignalingRoom] = {}


def get_or_create_room(room_id: str) -> SignalingRoom:
    if room_id not in _rooms:
        _rooms[room_id] = SignalingRoom(room_id)
    return _rooms[room_id]


def cleanup_room(room_id: str) -> None:
    room = _rooms.get(room_id)
    if room and room.is_empty:
        del _rooms[room_id]
        logger.info(f"[{room_id}] Room cleaned up")


# ── WebSocket Endpoint ────────────────────────────────────────────────────────


@router.websocket("/signaling/{room_id}")
async def signaling_endpoint(
    websocket: WebSocket,
    room_id: str,
    role: str = Query(..., pattern="^(shopper|customer)$"),
):
    """
    WebRTC signaling channel.

    Query params:
        role: "shopper" | "customer"

    Message types (JSON):
        → { "type": "offer",         "sdp": "<SDP string>" }
        → { "type": "answer",        "sdp": "<SDP string>" }
        → { "type": "ice-candidate", "candidate": { ... } }
        → { "type": "bye" }

    All messages are forwarded to the other peer in the room.
    """
    await websocket.accept()
    room = get_or_create_room(room_id)

    try:
        room.add_peer(role, websocket)
    except ValueError as e:
        await websocket.send_json({"type": "error", "message": str(e)})
        await websocket.close(code=4001)
        return

    # Notify the other peer that someone joined
    other = room.get_other_peer(role)
    if other:
        try:
            await other.send_json({
                "type": "peer-joined",
                "role": role,
                "room_id": room_id,
            })
        except Exception:
            pass

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON",
                })
                continue

            msg_type = message.get("type")
            if msg_type not in ("offer", "answer", "ice-candidate", "bye"):
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}",
                })
                continue

            logger.debug(f"[{room_id}] {role} → {msg_type}")

            # Handle bye – close session
            if msg_type == "bye":
                other = room.get_other_peer(role)
                if other:
                    try:
                        await other.send_json({"type": "bye", "role": role})
                    except Exception:
                        pass
                break

            # Forward to the other peer
            other = room.get_other_peer(role)
            if other:
                # Stamp the sender role so the receiver knows who sent it
                message["from_role"] = role
                try:
                    await other.send_json(message)
                except Exception as e:
                    logger.warning(
                        f"[{room_id}] Failed to forward to peer: {e}"
                    )
            else:
                # No peer yet – queue or notify
                await websocket.send_json({
                    "type": "waiting",
                    "message": "Waiting for the other peer to connect...",
                })

    except WebSocketDisconnect:
        logger.info(f"[{room_id}] {role} disconnected")
    except Exception as e:
        logger.error(f"[{room_id}] {role} error: {e}")
    finally:
        # Clean up
        room.remove_peer(role)

        # Notify remaining peer
        other = room.get_other_peer(role)
        if other:
            try:
                await other.send_json({
                    "type": "peer-left",
                    "role": role,
                })
            except Exception:
                pass

        cleanup_room(room_id)
