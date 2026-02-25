"""
VisionCart – Canvas Overlay WebSocket Handler

Handles real-time tap-to-highlight events from the Customer that are
rendered as AR overlays on the Shopper's video feed.

Includes the Coordinate Mapping system that transforms Customer screen
coordinates to the Shopper's camera frame coordinates.

Latency target: < 30ms signaling round-trip for overlay events.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Dict, List, Optional

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

router = APIRouter()
logger = logging.getLogger("visioncart.overlay")


# ── Coordinate Mapping Engine ─────────────────────────────────────────────────


class CoordinateMapper:
    """
    Maps Customer screen coordinates to Shopper camera frame coordinates.

    Three modes of operation (ordered by accuracy):
      1. Homography-based: Uses 4+ calibration point pairs to compute a
         perspective transform matrix. Best for fixed camera setups.
      2. Aspect-ratio corrected: Adjusts for different aspect ratios between
         Customer display and Shopper camera. Default for dynamic POV cameras.
      3. Direct passthrough: Normalized [0,1] coordinates pass through
         unchanged. Fallback when resolutions match.

    All input/output coordinates are normalized to [0, 1] range.
    """

    def __init__(self):
        self._homography_matrix: Optional[np.ndarray] = None
        self._customer_aspect: float = 16 / 9  # Default
        self._shopper_aspect: float = 16 / 9   # Default
        self._calibration_points: List[Dict] = []

    def set_resolutions(
        self,
        customer_width: int,
        customer_height: int,
        shopper_width: int,
        shopper_height: int,
    ) -> None:
        """Update aspect ratios for the mapping transform."""
        self._customer_aspect = customer_width / max(customer_height, 1)
        self._shopper_aspect = shopper_width / max(shopper_height, 1)
        logger.info(
            f"Resolution set: customer={customer_width}x{customer_height} "
            f"({self._customer_aspect:.2f}), "
            f"shopper={shopper_width}x{shopper_height} "
            f"({self._shopper_aspect:.2f})"
        )

    def calibrate(self, point_pairs: List[Dict]) -> bool:
        """
        Compute a homography matrix from 4+ corresponding point pairs.

        Args:
            point_pairs: List of dicts with keys:
                customer_x, customer_y: normalized coords on customer screen
                shopper_x, shopper_y:   corresponding coords in shopper frame

        Returns:
            True if calibration succeeded (rank-sufficient point pairs).
        """
        if len(point_pairs) < 4:
            logger.warning("Need at least 4 point pairs for homography calibration")
            return False

        self._calibration_points = point_pairs

        src_points = np.array(
            [[p["customer_x"], p["customer_y"]] for p in point_pairs],
            dtype=np.float64,
        )
        dst_points = np.array(
            [[p["shopper_x"], p["shopper_y"]] for p in point_pairs],
            dtype=np.float64,
        )

        try:
            # Compute homography using DLT (Direct Linear Transform)
            # This is the core of OpenCV's findHomography without the RANSAC
            self._homography_matrix = self._compute_homography(src_points, dst_points)
            logger.info(
                f"Homography calibrated with {len(point_pairs)} point pairs"
            )
            return True
        except np.linalg.LinAlgError:
            logger.error("Homography computation failed – degenerate point config")
            self._homography_matrix = None
            return False

    @staticmethod
    def _compute_homography(
        src: np.ndarray, dst: np.ndarray
    ) -> np.ndarray:
        """
        Direct Linear Transform (DLT) for homography estimation.
        Computes the 3×3 matrix H such that dst = H @ src (in homogeneous coords).
        """
        n = src.shape[0]
        A = []
        for i in range(n):
            x, y = src[i]
            u, v = dst[i]
            A.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
            A.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])

        A = np.array(A)
        _, _, Vt = np.linalg.svd(A)
        H = Vt[-1].reshape(3, 3)
        H /= H[2, 2]  # Normalize
        return H

    def map_coordinates(
        self, customer_x: float, customer_y: float
    ) -> Dict[str, float]:
        """
        Transform a Customer tap coordinate to Shopper frame coordinate.

        Args:
            customer_x: Normalized X position [0, 1] on customer screen.
            customer_y: Normalized Y position [0, 1] on customer screen.

        Returns:
            Dict with 'x' and 'y' keys – normalized Shopper frame coordinates.
        """
        # Mode 1: Homography (most accurate)
        if self._homography_matrix is not None:
            pt = np.array([customer_x, customer_y, 1.0])
            mapped = self._homography_matrix @ pt
            mapped /= mapped[2]  # De-homogenize
            return {
                "x": float(np.clip(mapped[0], 0.0, 1.0)),
                "y": float(np.clip(mapped[1], 0.0, 1.0)),
            }

        # Mode 2: Aspect-ratio correction
        if abs(self._customer_aspect - self._shopper_aspect) > 0.01:
            ratio = self._customer_aspect / self._shopper_aspect
            if ratio > 1:
                # Customer is wider → compress X, pad Y
                mapped_x = 0.5 + (customer_x - 0.5) * ratio
                mapped_y = customer_y
            else:
                # Customer is taller → compress Y, pad X
                mapped_x = customer_x
                mapped_y = 0.5 + (customer_y - 0.5) / ratio

            return {
                "x": float(np.clip(mapped_x, 0.0, 1.0)),
                "y": float(np.clip(mapped_y, 0.0, 1.0)),
            }

        # Mode 3: Direct passthrough (same aspect ratio)
        return {"x": customer_x, "y": customer_y}


# ── Overlay Event Types ───────────────────────────────────────────────────────


class OverlayEvent:
    """Represents a visual overlay event to be rendered on the Shopper's screen."""

    @staticmethod
    def tap_highlight(
        x: float,
        y: float,
        radius: float = 30.0,
        color: str = "#FF6B35",
        duration_ms: int = 3000,
    ) -> Dict:
        return {
            "type": "overlay",
            "shape": "circle_pulse",
            "x": x,
            "y": y,
            "radius": radius,
            "color": color,
            "duration_ms": duration_ms,
            "timestamp": time.time(),
        }

    @staticmethod
    def arrow_pointer(
        from_x: float,
        from_y: float,
        to_x: float,
        to_y: float,
        color: str = "#00D4FF",
        duration_ms: int = 5000,
    ) -> Dict:
        return {
            "type": "overlay",
            "shape": "arrow",
            "from_x": from_x,
            "from_y": from_y,
            "to_x": to_x,
            "to_y": to_y,
            "color": color,
            "duration_ms": duration_ms,
            "timestamp": time.time(),
        }

    @staticmethod
    def text_label(
        x: float,
        y: float,
        text: str,
        color: str = "#FFFFFF",
        bg_color: str = "#000000AA",
        duration_ms: int = 5000,
    ) -> Dict:
        return {
            "type": "overlay",
            "shape": "text",
            "x": x,
            "y": y,
            "text": text,
            "color": color,
            "bg_color": bg_color,
            "duration_ms": duration_ms,
            "timestamp": time.time(),
        }

    @staticmethod
    def bounding_box(
        x: float,
        y: float,
        width: float,
        height: float,
        label: str = "",
        color: str = "#00FF88",
        duration_ms: int = 2000,
    ) -> Dict:
        return {
            "type": "overlay",
            "shape": "bbox",
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "label": label,
            "color": color,
            "duration_ms": duration_ms,
            "timestamp": time.time(),
        }


# ── Room Connections ──────────────────────────────────────────────────────────

_overlay_rooms: Dict[str, Dict[str, WebSocket]] = {}
_coordinate_mappers: Dict[str, CoordinateMapper] = {}


def get_mapper(room_id: str) -> CoordinateMapper:
    if room_id not in _coordinate_mappers:
        _coordinate_mappers[room_id] = CoordinateMapper()
    return _coordinate_mappers[room_id]


# ── WebSocket Endpoint ────────────────────────────────────────────────────────


@router.websocket("/overlay/{room_id}")
async def overlay_endpoint(
    websocket: WebSocket,
    room_id: str,
    role: str = Query(..., pattern="^(shopper|customer)$"),
):
    """
    Canvas overlay channel for real-time tap-to-highlight.

    Customer sends:
      → { "type": "tap", "x": 0.45, "y": 0.32, "radius": 30, "color": "#FF6B35" }
      → { "type": "arrow", "from_x": 0.2, "from_y": 0.3, "to_x": 0.6, "to_y": 0.7 }
      → { "type": "text", "x": 0.5, "y": 0.1, "text": "Check this one!" }
      → { "type": "set_resolution", "width": 1920, "height": 1080 }
      → { "type": "calibrate", "points": [...] }

    Shopper receives:
      ← { "type": "overlay", "shape": "circle_pulse", "x": ..., "y": ..., ... }

    Both can receive:
      ← { "type": "ai_overlay", "shape": "bbox", ... }  (from AI engine)
    """
    await websocket.accept()

    if room_id not in _overlay_rooms:
        _overlay_rooms[room_id] = {}
    _overlay_rooms[room_id][role] = websocket

    mapper = get_mapper(room_id)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = message.get("type")

            # ── Resolution configuration ──
            if msg_type == "set_resolution":
                w, h = message.get("width", 1920), message.get("height", 1080)
                if role == "customer":
                    # Store customer resolution; keep existing shopper values
                    mapper._customer_aspect = w / max(h, 1)
                else:
                    # Store shopper resolution; keep existing customer values
                    mapper._shopper_aspect = w / max(h, 1)
                logger.info(
                    f"[{room_id}] {role} resolution set to {w}x{h}"
                )
                continue

            # ── Calibration ──
            if msg_type == "calibrate":
                points = message.get("points", [])
                success = mapper.calibrate(points)
                await websocket.send_json({
                    "type": "calibration_result",
                    "success": success,
                    "num_points": len(points),
                })
                continue

            # ── Customer tap → Shopper overlay ──
            if role == "customer" and msg_type == "tap":
                mapped = mapper.map_coordinates(
                    message.get("x", 0.5),
                    message.get("y", 0.5),
                )
                overlay = OverlayEvent.tap_highlight(
                    x=mapped["x"],
                    y=mapped["y"],
                    radius=message.get("radius", 30.0),
                    color=message.get("color", "#FF6B35"),
                    duration_ms=message.get("duration_ms", 3000),
                )
                # Send to shopper
                shopper_ws = _overlay_rooms.get(room_id, {}).get("shopper")
                if shopper_ws:
                    await shopper_ws.send_json(overlay)
                continue

            if role == "customer" and msg_type == "arrow":
                from_mapped = mapper.map_coordinates(
                    message.get("from_x", 0), message.get("from_y", 0)
                )
                to_mapped = mapper.map_coordinates(
                    message.get("to_x", 1), message.get("to_y", 1)
                )
                overlay = OverlayEvent.arrow_pointer(
                    from_x=from_mapped["x"],
                    from_y=from_mapped["y"],
                    to_x=to_mapped["x"],
                    to_y=to_mapped["y"],
                )
                shopper_ws = _overlay_rooms.get(room_id, {}).get("shopper")
                if shopper_ws:
                    await shopper_ws.send_json(overlay)
                continue

            if role == "customer" and msg_type == "text":
                mapped = mapper.map_coordinates(
                    message.get("x", 0.5), message.get("y", 0.5)
                )
                overlay = OverlayEvent.text_label(
                    x=mapped["x"],
                    y=mapped["y"],
                    text=message.get("text", ""),
                )
                shopper_ws = _overlay_rooms.get(room_id, {}).get("shopper")
                if shopper_ws:
                    await shopper_ws.send_json(overlay)
                continue

    except WebSocketDisconnect:
        logger.info(f"[{room_id}] {role} disconnected from overlay")
    finally:
        if room_id in _overlay_rooms:
            _overlay_rooms[room_id].pop(role, None)
            if not _overlay_rooms[room_id]:
                del _overlay_rooms[room_id]
                _coordinate_mappers.pop(room_id, None)
