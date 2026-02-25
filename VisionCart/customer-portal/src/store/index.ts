/**
 * VisionCart – Zustand State Store
 *
 * Global state management for the Customer Portal.
 * Uses Zustand for lightweight, hook-based state with minimal re-renders.
 */

import { create } from 'zustand';

// ── Types ────────────────────────────────────────────────────────────────────

export interface CartItem {
  itemId: string;
  inventoryId: string;
  name: string;
  quantityRequested: number;
  quantityPicked: number;
  unitPrice: number;
  status: 'pending' | 'found' | 'picked' | 'not_found' | 'substituted';
  freshnessScore: number | null;
  freshnessGrade: string | null;
}

export interface BudgetAlert {
  severity: 'warning' | 'critical';
  budgetPercent: number;
  currentTotal: number;
  budgetLimit: number;
  remaining: number;
  message: string;
  timestamp: number;
}

export interface Transcript {
  id: string;
  text: string;
  speaker: 'customer' | 'shopper';
  confidence: number;
  timestamp: number;
}

export interface SessionInfo {
  sessionId: string;
  orderId: string;
  status: 'pending' | 'active' | 'completed';
  signalingRoom: string;
  shopperName: string;
}

export interface CustomerAccount {
  id: number;
  username: string;
  address_line_1: string | null;
  address_line_2: string | null;
  state: string | null;
  zip_code: string | null;
}

// ── Store ────────────────────────────────────────────────────────────────────

interface VisionCartStore {
  // Auth
  isLoggedIn: boolean;
  customer: CustomerAccount | null;
  login: (customer: CustomerAccount) => void;
  logout: () => void;

  // Session
  session: SessionInfo | null;
  setSession: (session: SessionInfo) => void;

  // Cart
  cartItems: CartItem[];
  currentTotal: number;
  budgetLimit: number;
  budgetPercent: number;
  currency: string;
  setCartState: (items: CartItem[], total: number, limit: number, percent: number) => void;
  updateItemStatus: (itemId: string, status: CartItem['status'], freshnessScore?: number) => void;

  // Budget
  budgetAlerts: BudgetAlert[];
  addBudgetAlert: (alert: BudgetAlert) => void;
  dismissAlert: (timestamp: number) => void;

  // Transcripts
  transcripts: Transcript[];
  addTranscript: (transcript: Transcript) => void;

  // UI
  isConnected: boolean;
  latencyMs: number;
  setConnectionState: (connected: boolean, latency?: number) => void;

  // AI Detections
  lastDetections: Array<{
    label: string;
    confidence: number;
    freshness?: number;
  }>;
  setDetections: (detections: VisionCartStore['lastDetections']) => void;
}

export const useStore = create<VisionCartStore>((set) => ({
  // ── Auth ──
  isLoggedIn: false,
  customer: null,
  login: (customer) => set({ isLoggedIn: true, customer }),
  logout: () => set({ isLoggedIn: false, customer: null }),

  // ── Session ──
  session: null,
  setSession: (session) => set({ session }),

  // ── Cart ──
  cartItems: [],
  currentTotal: 0,
  budgetLimit: 100,
  budgetPercent: 0,
  currency: 'USD',
  setCartState: (items, total, limit, percent) =>
    set({
      cartItems: items,
      currentTotal: total,
      budgetLimit: limit,
      budgetPercent: percent,
    }),
  updateItemStatus: (itemId, status, freshnessScore) =>
    set((state) => ({
      cartItems: state.cartItems.map((item) =>
        item.itemId === itemId
          ? { ...item, status, freshnessScore: freshnessScore ?? item.freshnessScore }
          : item
      ),
    })),

  // ── Budget ──
  budgetAlerts: [],
  addBudgetAlert: (alert) =>
    set((state) => ({
      budgetAlerts: [...state.budgetAlerts.slice(-10), alert], // Keep last 10
    })),
  dismissAlert: (timestamp) =>
    set((state) => ({
      budgetAlerts: state.budgetAlerts.filter((a) => a.timestamp !== timestamp),
    })),

  // ── Transcripts ──
  transcripts: [],
  addTranscript: (transcript) =>
    set((state) => ({
      transcripts: [...state.transcripts.slice(-50), transcript], // Keep last 50
    })),

  // ── UI ──
  isConnected: false,
  latencyMs: 0,
  setConnectionState: (connected, latency) =>
    set({ isConnected: connected, latencyMs: latency ?? 0 }),

  // ── AI ──
  lastDetections: [],
  setDetections: (detections) => set({ lastDetections: detections }),
}));
