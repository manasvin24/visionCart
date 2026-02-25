# VisionCart – Database Schema

## Entity-Relationship Diagram

```mermaid
erDiagram
    USERS ||--o{ SESSIONS : participates_in
    USERS ||--o{ ORDERS : places
    ORDERS ||--|{ ORDER_ITEMS : contains
    INVENTORY ||--o{ ORDER_ITEMS : references
    SESSIONS ||--|{ SESSION_EVENTS : logs
    SESSIONS ||--|| ORDERS : fulfills
    ORDERS ||--o{ SUBSTITUTIONS : has
    INVENTORY ||--o{ SUBSTITUTIONS : original
    INVENTORY ||--o{ SUBSTITUTIONS : replacement
    USERS ||--o{ BUDGET_ALERTS : receives

    USERS {
        text id PK
        varchar email UK
        enum role "shopper | customer"
        varchar display_name
        varchar phone
        json preferences
        timestamp created_at
        timestamp updated_at
    }

    SESSIONS {
        text id PK
        text customer_id FK
        text shopper_id FK
        text order_id FK
        enum status "pending | active | paused | completed | cancelled"
        varchar signaling_room
        json ice_servers
        json quality_metrics
        timestamp started_at
        timestamp ended_at
        timestamp created_at
    }

    SESSION_EVENTS {
        bigint id PK
        text session_id FK
        enum event_type "tap | voice | ai_detection | item_pick | item_return | freshness_alert | budget_alert"
        json payload
        float timestamp_offset_ms
        timestamp created_at
    }

    ORDERS {
        text id PK
        text customer_id FK
        enum status "draft | in_progress | completed | cancelled"
        decimal budget_limit
        decimal current_total
        varchar currency
        json delivery_address
        text notes
        timestamp created_at
        timestamp updated_at
    }

    ORDER_ITEMS {
        bigint id PK
        text order_id FK
        text inventory_id FK
        int quantity_requested
        int quantity_picked
        enum status "pending | found | picked | not_found | substituted"
        decimal unit_price
        float freshness_score
        json ai_metadata
        timestamp picked_at
        timestamp created_at
    }

    INVENTORY {
        text id PK
        varchar sku UK
        varchar name
        varchar category
        varchar brand
        decimal price
        varchar unit
        varchar image_url
        json nutrition_info
        json detection_labels
        boolean in_stock
        timestamp updated_at
    }

    SUBSTITUTIONS {
        bigint id PK
        text order_id FK
        text original_item_id FK
        text replacement_item_id FK
        enum status "suggested | approved | rejected"
        varchar reason
        decimal price_difference
        timestamp created_at
    }

    BUDGET_ALERTS {
        bigint id PK
        text order_id FK
        text user_id FK
        decimal threshold_percent
        decimal current_percent
        decimal cart_total
        decimal budget_limit
        boolean acknowledged
        timestamp created_at
    }
```

## Table Details

### `users`
Primary identity table. Supports both `shopper` and `customer` roles. The `preferences` JSON column stores notification settings, default budget, preferred stores, etc.

### `sessions`
Represents a live shopping session. Links one customer to one shopper with a specific order. The `signaling_room` is the WebSocket room ID for SDP/ICE exchange. `quality_metrics` tracks bitrate, frame drops, and latency samples.

### `session_events`
Append-only event log for each session. `timestamp_offset_ms` is relative to `session.started_at` for replay synchronization. The `payload` JSON varies by `event_type`:

- **tap**: `{ "x": 0.45, "y": 0.32, "radius": 30 }`
- **voice**: `{ "transcript": "Check the expiry", "confidence": 0.94 }`
- **ai_detection**: `{ "label": "banana", "confidence": 0.87, "bbox": [x,y,w,h], "freshness": 0.72 }`
- **item_pick**: `{ "order_item_id": "...", "inventory_id": "..." }`
- **budget_alert**: `{ "percent": 92, "total": 46.50, "limit": 50.00 }`

### `orders`
Shopping order with budget tracking. `current_total` is denormalized and updated via triggers/application logic on every item pick.

### `order_items`
Line items linking an order to inventory. `ai_metadata` stores the last detection context (bounding box, freshness breakdown, image snapshot URL).

### `inventory`
Store product catalog. `detection_labels` maps CV model class names to this product (e.g., `["banana", "cavendish_banana"]`). Updated via store API integration or manual import.

### `substitutions`
Tracks when the AI or shopper suggests a replacement for an unavailable/poor-quality item.

### `budget_alerts`
Persisted alerts for audit. Created when `current_total / budget_limit` exceeds the configured threshold.

## Indexes

```sql
-- Performance-critical queries
CREATE INDEX idx_sessions_status ON sessions(status);
CREATE INDEX idx_sessions_customer ON sessions(customer_id);
CREATE INDEX idx_sessions_shopper ON sessions(shopper_id);
CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_order_items_status ON order_items(order_id, status);
CREATE INDEX idx_session_events_session ON session_events(session_id, created_at);
CREATE INDEX idx_session_events_type ON session_events(session_id, event_type);
CREATE INDEX idx_inventory_sku ON inventory(sku);
CREATE INDEX idx_inventory_category ON inventory(category);
```
