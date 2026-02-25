"""
VisionCart – Video Frame Relay WebSocket

Relays JPEG frames from the Shopper's camera to the Customer's browser.
This is a lightweight MJPEG-over-WebSocket bridge for Expo Go environments
where native WebRTC is unavailable.

Protocol:
  - Shopper sends: binary JPEG frame data
  - Server broadcasts: binary JPEG frame data to all customers in the session
  - Either side can send JSON: { "type": "ping" } for keep-alive
"""

from __future__ import annotations

import logging
import time
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

router = APIRouter()
logger = logging.getLogger("visioncart.video_relay")

# Session → role → WebSocket
_connections: Dict[str, Dict[str, Set[WebSocket]]] = {}


@router.websocket("/video/{session_id}")
async def video_relay_endpoint(
    websocket: WebSocket,
    session_id: str,
    role: str = Query(..., pattern="^(shopper|customer)$"),
):
    """
    Video frame relay channel.

    Shopper sends binary JPEG frames → server forwards to all customers.
    Minimal overhead: no JSON parsing for frame data (binary passthrough).
    """
    await websocket.accept()

    # Register connection
    if session_id not in _connections:
        _connections[session_id] = {"shopper": set(), "customer": set()}
    _connections[session_id][role].add(websocket)

    logger.info(f"[{session_id}] {role} connected to video relay")

    try:
        while True:
            message = await websocket.receive()

            frame_bytes: bytes | None = None

            # Binary frame from shopper
            if "bytes" in message and message["bytes"] and role == "shopper":
                frame_bytes = message["bytes"]

            # Base64-text frame from shopper (faster path from Expo)
            elif "text" in message and message["text"] and role == "shopper":
                import base64
                txt = message["text"]
                # Skip JSON keep-alive messages
                if txt.startswith("{"):
                    continue
                try:
                    frame_bytes = base64.b64decode(txt)
                except Exception:
                    continue

            if frame_bytes and role == "shopper":
                customers = _connections.get(session_id, {}).get("customer", set())
                dead = []
                for customer_ws in customers:
                    try:
                        await customer_ws.send_bytes(frame_bytes)
                    except Exception:
                        dead.append(customer_ws)
                for d in dead:
                    customers.discard(d)

    except WebSocketDisconnect:
        logger.info(f"[{session_id}] {role} disconnected from video relay")
    except Exception as e:
        logger.warning(f"[{session_id}] {role} video relay error: {e}")
    finally:
        if session_id in _connections and role in _connections[session_id]:
            _connections[session_id][role].discard(websocket)
            # Cleanup empty sessions
            if not _connections[session_id]["shopper"] and not _connections[session_id]["customer"]:
                del _connections[session_id]
