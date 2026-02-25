"""
VisionCart – Quality Inspection Endpoint  (Grok Vision API)

Customer clicks on the live video feed → browser captures that frame →
sends it to this endpoint → Grok vision model analyses the image →
result is returned AND pushed to the shopper via state-sync WS.

Flow:
  POST /api/inspect/{session_id}
    Body: multipart  image=<jpeg bytes>
    Response: { item, score, grade, recommendation, ... }
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import time
from typing import Any, Dict

import httpx
from fastapi import APIRouter, File, UploadFile, Path as PathParam

router = APIRouter()
logger = logging.getLogger("visioncart.inspect")

# ── Grok configuration ───────────────────────────────────────────────────────

XAI_API_KEY = os.getenv("XAI_API_KEY", "")
XAI_BASE_URL = "https://api.x.ai/v1"
# grok-2-vision-1212 – fast vision model, meets 1-2 s latency target
GROK_VISION_MODEL = os.getenv("GROK_VISION_MODEL", "grok-2-vision-1212")

SYSTEM_PROMPT = """\
You are an expert grocery quality inspector.  You will receive a photo taken
by a shopper in a grocery store.  Identify the product(s) visible and assess
their quality / freshness.

Respond ONLY with valid JSON (no markdown, no code fences) using this schema:
{
  "item": "<name of the primary product, e.g. Banana, Apple, Tomato>",
  "score": <float 0-1, where 1 = perfect quality>,
  "grade": "<one of: Excellent, Good, Fair, Poor, Bad>",
  "recommendation": "<one-line advice for the shopper>",
  "is_bruised": <true | false>,
  "details": "<optional short description of defects or positive signs>"
}

Rules:
- 'score' must reflect visual quality: colour uniformity, firmness, bruising,
  mould, dryness, over-ripeness, spots, wrinkles, etc.
- If the image does not show a recognisable grocery/produce item, return:
  {"item":"unknown","score":0.5,"grade":"N/A","recommendation":"No clear grocery item detected. Try again.","is_bruised":false,"details":""}
- Keep 'recommendation' under 120 characters.
"""

# ── Shared WS state import (to push alerts to shopper) ───────────────────────

from app.ws.state_sync import _session_connections


async def _push_quality_alert(session_id: str, alert: Dict[str, Any]):
    """Send a quality_alert message to all peers connected to this session."""
    connections = _session_connections.get(session_id, {})
    if not connections:
        logger.warning(f"[{session_id}] No WS connections found – cannot push alert")
        return
    payload = json.dumps(alert)
    dead = []
    for role, ws in list(connections.items()):
        try:
            await ws.send_text(payload)
            logger.info(f"[{session_id}] Quality alert sent to {role}")
        except Exception as e:
            logger.warning(f"[{session_id}] Failed to send alert to {role}: {e}")
            dead.append(role)
    for role in dead:
        connections.pop(role, None)


def _parse_grok_json(text: str) -> Dict[str, Any]:
    """Best-effort extraction of the JSON object from Grok's reply."""
    # Strip possible markdown code fences
    text = re.sub(r"^```(?:json)?", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"```$", "", text.strip(), flags=re.MULTILINE)
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        # Try to find a JSON object inside the text
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            return json.loads(m.group())
        raise


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/inspect/{session_id}")
async def inspect_frame(
    session_id: str = PathParam(...),
    image: UploadFile = File(...),
):
    """
    Receive a JPEG frame from the customer portal, send it to the Grok
    vision model for quality analysis, and push results to the shopper.
    """
    t0 = time.time()

    if not XAI_API_KEY:
        return {"error": "XAI_API_KEY is not set on the backend. Cannot call Grok."}

    # ── Encode image to base64 data-URL ──
    raw_bytes = await image.read()
    b64 = base64.b64encode(raw_bytes).decode("ascii")
    data_url = f"data:image/jpeg;base64,{b64}"

    # ── Call Grok Vision via OpenAI-compatible chat/completions ──
    payload = {
        "model": GROK_VISION_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url, "detail": "high"},
                    },
                    {
                        "type": "text",
                        "text": "Please inspect this grocery product and assess its quality.",
                    },
                ],
            },
        ],
        "temperature": 0.2,
        "max_tokens": 300,
    }

    headers = {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{XAI_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPStatusError as exc:
        logger.error(f"[{session_id}] Grok API HTTP error: {exc.response.status_code} – {exc.response.text[:300]}")
        return {"error": f"Grok API error: {exc.response.status_code}"}
    except httpx.RequestError as exc:
        logger.error(f"[{session_id}] Grok API request error: {exc}")
        return {"error": "Failed to reach Grok API"}

    # ── Parse Grok response ──
    raw_reply = body["choices"][0]["message"]["content"]
    logger.info(f"[{session_id}] Grok raw reply: {raw_reply[:200]}")

    try:
        result = _parse_grok_json(raw_reply)
    except (json.JSONDecodeError, Exception) as exc:
        logger.error(f"[{session_id}] Failed to parse Grok JSON: {exc}\nRaw: {raw_reply}")
        result = {
            "item": "unknown",
            "score": 0.5,
            "grade": "N/A",
            "recommendation": "Could not parse AI response. Try again.",
            "is_bruised": False,
            "details": raw_reply[:200],
        }

    # Normalise fields
    score = float(result.get("score", 0.5))
    item = result.get("item", "unknown")
    grade = result.get("grade", "N/A")
    recommendation = result.get("recommendation", "")
    is_bruised = bool(result.get("is_bruised", False))
    details = result.get("details", "")

    elapsed_ms = round((time.time() - t0) * 1000)

    # ── Push quality alert to shopper ──
    alert = {
        "type": "quality_alert",
        "session_id": session_id,
        "item": item,
        "score": score,
        "grade": grade,
        "recommendation": recommendation,
        "is_bruised": is_bruised,
        "details": details,
        "timestamp": time.time(),
    }
    await _push_quality_alert(session_id, alert)
    logger.info(f"[{session_id}] Quality alert: {item} scored {score:.2f} ({grade})")

    return {
        "session_id": session_id,
        "item": item,
        "score": score,
        "grade": grade,
        "recommendation": recommendation,
        "is_bruised": is_bruised,
        "details": details,
        "inference_ms": elapsed_ms,
        "quality_alert_sent": True,
        "model": GROK_VISION_MODEL,
    }
