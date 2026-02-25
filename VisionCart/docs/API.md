# VisionCart – API Documentation

## Base URL

```
Development: http://localhost:8000
Production:  https://api.visioncart.io
```

## Authentication

This MVP does not implement authentication. All endpoints are publicly accessible.

---

## REST API Endpoints

### 1. Users

#### `POST /api/users/register`

Create a new user account.

**Request:**
```json
{
  "email": "customer@example.com",
  "role": "customer",
  "display_name": "Jane Smith",
  "phone": "+1-555-0100"
}
```

**Response:** `201 Created`
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "customer@example.com",
  "role": "customer",
  "display_name": "Jane Smith",
  "phone": "+1-555-0100",
  "created_at": "2026-02-21T10:30:00Z"
}
```

#### `GET /api/users/users`

List all users, optionally filtered by role.

**Query params:** `?role=shopper` or `?role=customer`

**Response:** `200 OK` – Array of user objects.

#### `GET /api/users/users/{user_id}`

Get a single user by ID.

**Response:** `200 OK` – User object.

---

### 2. Sessions

#### `POST /api/sessions/`

Create a new live shopping session (initiated by Customer).

**Request:**
```json
{
  "order_id": "660e8400-e29b-41d4-a716-446655440001"
}
```

**Response:** `201 Created`
```json
{
  "id": "770e8400-e29b-41d4-a716-446655440002",
  "customer_id": "550e8400-e29b-41d4-a716-446655440000",
  "shopper_id": null,
  "order_id": "660e8400-e29b-41d4-a716-446655440001",
  "status": "pending",
  "signaling_room": "vc-a1b2c3d4e5f6",
  "ice_servers": [
    { "urls": "stun:stun.l.google.com:19302" }
  ],
  "created_at": "2026-02-21T10:35:00Z",
  "started_at": null
}
```

#### `GET /api/sessions/{session_id}`

Get session details including ICE server configuration.

**Response:** `200 OK` – Same as above.

#### `POST /api/sessions/{session_id}/join`

Shopper joins an existing session. Transitions status to `active`.

**Response:** `200 OK`
```json
{
  "id": "770e8400-...",
  "status": "active",
  "shopper_id": "880e8400-...",
  "started_at": "2026-02-21T10:36:00Z"
}
```

#### `POST /api/sessions/{session_id}/end`

End a live session. Transitions status to `completed`.

**Response:** `200 OK`

---

### 3. Orders

#### `POST /api/orders/`

Create a shopping order with budget and item list.

**Request:**
```json
{
  "budget_limit": 50.00,
  "currency": "USD",
  "notes": "Prefer organic when available",
  "items": [
    { "inventory_id": "inv-001", "quantity_requested": 1 },
    { "inventory_id": "inv-002", "quantity_requested": 3 },
    { "inventory_id": "inv-003", "quantity_requested": 2 }
  ]
}
```

**Response:** `201 Created`
```json
{
  "id": "660e8400-...",
  "customer_id": "550e8400-...",
  "status": "draft",
  "budget_limit": 50.00,
  "current_total": 0.00,
  "currency": "USD",
  "items": [
    {
      "id": 1,
      "inventory_id": "inv-001",
      "quantity_requested": 1,
      "quantity_picked": 0,
      "status": "pending",
      "unit_price": 1.29,
      "freshness_score": null
    }
  ]
}
```

#### `GET /api/orders/{order_id}`

Get order details with all items.

#### `POST /api/orders/{order_id}/items/{item_id}/pick`

Mark an item as picked by the shopper.

**Query params:**
- `freshness_score` (float, optional): AI freshness score [0, 1]

**Response:** `200 OK`
```json
{
  "id": 1,
  "status": "picked",
  "quantity_picked": 1,
  "freshness_score": 0.87,
  "picked_at": "2026-02-21T10:40:00Z"
}
```

---

### 4. Inventory

#### `GET /api/inventory/`

Search and list inventory items.

**Query params:**
- `search` (string): Full-text search on name, brand, SKU
- `category` (string): Filter by category
- `in_stock` (bool): Filter by stock status (default: true)
- `limit` (int): Max results (default: 50, max: 200)
- `offset` (int): Pagination offset

**Response:** `200 OK`
```json
[
  {
    "id": "inv-001",
    "sku": "BAN-ORG-001",
    "name": "Organic Bananas",
    "category": "produce",
    "brand": "Nature's Best",
    "price": 1.29,
    "unit": "bunch",
    "in_stock": true
  }
]
```

#### `GET /api/inventory/{item_id}`

Get a single inventory item.

---

### 5. Health Check

#### `GET /health`

**Response:** `200 OK`
```json
{
  "status": "healthy",
  "service": "visioncart-api",
  "version": "0.1.0"
}
```

---

## WebSocket Protocols

### 1. Signaling – `ws://host/ws/signaling/{room_id}?role=<shopper|customer>`

WebRTC SDP and ICE exchange channel.

| Direction | Type | Payload |
|-----------|------|---------|
| → | `offer` | `{ "type": "offer", "sdp": "<SDP string>" }` |
| → | `answer` | `{ "type": "answer", "sdp": "<SDP string>" }` |
| ↔ | `ice-candidate` | `{ "type": "ice-candidate", "candidate": { "candidate": "...", "sdpMid": "...", "sdpMLineIndex": 0 } }` |
| ← | `peer-joined` | `{ "type": "peer-joined", "role": "shopper" }` |
| ← | `peer-left` | `{ "type": "peer-left", "role": "shopper" }` |
| → | `bye` | `{ "type": "bye" }` |
| ← | `waiting` | `{ "type": "waiting", "message": "..." }` |
| ← | `error` | `{ "type": "error", "message": "..." }` |

### 2. Overlay – `ws://host/ws/overlay/{room_id}?role=<shopper|customer>`

Canvas overlay / tap-to-highlight channel.

| Direction | Type | Payload |
|-----------|------|---------|
| Customer → | `tap` | `{ "type": "tap", "x": 0.45, "y": 0.32, "radius": 30, "color": "#FF6B35" }` |
| Customer → | `arrow` | `{ "type": "arrow", "from_x": 0.2, "from_y": 0.3, "to_x": 0.6, "to_y": 0.7 }` |
| Customer → | `text` | `{ "type": "text", "x": 0.5, "y": 0.1, "text": "Check this one!" }` |
| Either → | `set_resolution` | `{ "type": "set_resolution", "width": 1920, "height": 1080 }` |
| Customer → | `calibrate` | `{ "type": "calibrate", "points": [{"customer_x": 0.1, "customer_y": 0.1, "shopper_x": 0.12, "shopper_y": 0.11}, ...] }` |
| → Shopper | `overlay` | `{ "type": "overlay", "shape": "circle_pulse", "x": 0.45, "y": 0.32, "radius": 30, "color": "#FF6B35", "duration_ms": 3000 }` |
| ← | `calibration_result` | `{ "type": "calibration_result", "success": true, "num_points": 4 }` |

### 3. State Sync – `ws://host/ws/state/{session_id}?role=<shopper|customer>`

Real-time cart and budget synchronization.

| Direction | Type | Payload |
|-----------|------|---------|
| → | `init_cart` | `{ "type": "init_cart", "order_id": "...", "items": [...], "budget_limit": 50.00 }` |
| → | `item_picked` | `{ "type": "item_picked", "item_id": "1", "freshness_score": 0.85 }` |
| → | `item_returned` | `{ "type": "item_returned", "item_id": "1" }` |
| → | `item_not_found` | `{ "type": "item_not_found", "item_id": "7" }` |
| → | `request_state` | `{ "type": "request_state" }` |
| ← Broadcast | `cart_state` | `{ "type": "cart_state", "items": [...], "current_total": 14.26, "budget_limit": 50.00, "budget_percent": 28.5 }` |
| ← Broadcast | `budget_alert` | `{ "type": "budget_alert", "severity": "warning", "budget_percent": 92, "message": "..." }` |
| ← Broadcast | `substitution_suggestion` | `{ "type": "substitution_suggestion", "original_item": {...}, "reason": "Low freshness", "alternatives": [...] }` |

---

## Error Responses

All error responses follow the format:

```json
{
  "detail": "Human-readable error message"
}
```

| Status | Meaning |
|--------|---------|
| 400 | Bad Request – Invalid input |
| 401 | Unauthorized – Missing or invalid token |
| 404 | Not Found – Resource doesn't exist |
| 409 | Conflict – Duplicate or invalid state transition |
| 422 | Validation Error – Schema mismatch |
| 500 | Internal Server Error |

---

## Rate Limits

| Endpoint Type | Limit |
|---------------|-------|
| REST API | 100 req/min per user |
| WebSocket messages | 60 msg/sec per connection |
| Voice chunks | 10 chunks/sec (Whisper API) |
