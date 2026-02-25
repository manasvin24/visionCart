/**
 * VisionCart – API & WebSocket Service Layer
 */

const API_BASE = '/api';

// ── REST API ─────────────────────────────────────────────────────────────────

export const api = {
  async createSession(orderId?: string) {
    const res = await fetch(`${API_BASE}/sessions/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ order_id: orderId }),
    });
    if (!res.ok) throw new Error(`Create session failed: ${res.status}`);
    return res.json();
  },

  async getSession(sessionId: string) {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}`);
    if (!res.ok) throw new Error(`Get session failed: ${res.status}`);
    return res.json();
  },

  async createOrder(data: {
    budget_limit: number;
    currency?: string;
    items?: Array<{ inventory_id: string; quantity_requested: number }>;
  }) {
    const res = await fetch(`${API_BASE}/orders/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error(`Create order failed: ${res.status}`);
    return res.json();
  },

  async getOrder(orderId: string) {
    const res = await fetch(`${API_BASE}/orders/${orderId}`);
    if (!res.ok) throw new Error(`Get order failed: ${res.status}`);
    return res.json();
  },

  async searchInventory(query?: string, category?: string) {
    const params = new URLSearchParams();
    if (query) params.set('search', query);
    if (category) params.set('category', category);
    const res = await fetch(`${API_BASE}/inventory/?${params}`);
    if (!res.ok) throw new Error(`Search inventory failed: ${res.status}`);
    return res.json();
  },
};

// ── WebSocket Connections ────────────────────────────────────────────────────

export function createOverlaySocket(
  roomId: string,
  role: 'shopper' | 'customer'
): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  return new WebSocket(`${protocol}//${host}/ws/overlay/${roomId}?role=${role}`);
}

export function createStateSyncSocket(
  sessionId: string,
  role: 'shopper' | 'customer'
): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  return new WebSocket(`${protocol}//${host}/ws/state/${sessionId}?role=${role}`);
}
