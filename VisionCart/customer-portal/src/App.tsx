/**
 * VisionCart – Customer Portal Main App Component
 *
 * Layout: Video feed (left) + Sidebar (right)
 *   - Video panel with interactive canvas overlay
 *   - Shopping list with live status updates
 *   - Budget tracker with real-time alerts
 *   - Voice transcript feed
 *
 * Connects to backend via WebSocket for real-time state sync with Shopper App.
 */

import React, { useEffect, useRef, useState } from 'react';
import { useStore } from './store';
import AuthScreen from './AuthScreen';

// ── Config ───────────────────────────────────────────────────────────────────
// Use same-origin WebSocket (Nginx proxies /ws/ to backend)
const WS_BASE = `ws://${window.location.host}/ws/state`;
const VIDEO_WS_BASE = `ws://${window.location.host}/ws/video`;
const SESSION_ID = 'demo-session';


// ── Main Portal Component ────────────────────────────────────────────────────

function CustomerPortal() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const store = useStore();
  const [hasVideoFeed, setHasVideoFeed] = useState(false);
  const hasVideoFeedRef = useRef(false);
  const [isInspecting, setIsInspecting] = useState(false);
  const [inspectionResult, setInspectionResult] = useState<any>(null);
  const lastFrameBlobRef = useRef<Blob | null>(null);
  const stateWsRef = useRef<WebSocket | null>(null);
  const [promptText, setPromptText] = useState('');

  // Voice recording state (speech-to-text)
  const [isRecording, setIsRecording] = useState(false);
  const [recordedText, setRecordedText] = useState('');
  const recognitionRef = useRef<any>(null);

  // New item input
  const [newItemName, setNewItemName] = useState('');
  const [newItemPrice, setNewItemPrice] = useState('');

  // Initialize + connect to backend WebSocket
  useEffect(() => {
    store.setSession({
      sessionId: SESSION_ID,
      orderId: 'demo-order',
      status: 'active',
      signalingRoom: 'vc-demo-room',
      shopperName: 'Alex M.',
    });

    // ── WebSocket: real-time cart sync with Shopper App ──
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout>;

    const connect = () => {
      const url = `${WS_BASE}/${SESSION_ID}?role=customer`;
      console.log('[WS] Customer connecting to', url);
      ws = new WebSocket(url);

      ws.onopen = () => {
        console.log('[WS] Customer connected ✅');
        store.setConnectionState(true, 42);
        stateWsRef.current = ws;
        // Request current state from server
        ws?.send(JSON.stringify({ type: 'request_state' }));
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'cart_state') {
            // Map server items to store format
            const items = msg.items.map((si: any) => ({
              itemId: si.item_id,
              inventoryId: si.inventory_id,
              name: si.name,
              quantityRequested: si.quantity_requested,
              quantityPicked: si.quantity_picked,
              unitPrice: si.unit_price,
              status: si.status,
              freshnessScore: si.freshness_score,
              freshnessGrade: si.freshness_details?.grade ?? (
                si.freshness_score !== null
                  ? (si.freshness_score >= 0.85 ? 'excellent' : si.freshness_score >= 0.65 ? 'good' : 'fair')
                  : null
              ),
            }));
            store.setCartState(items, msg.current_total, msg.budget_limit, msg.budget_percent);
            console.log('[WS] Cart state updated:', msg.items_picked, '/', msg.items_total, 'picked');
          } else if (msg.type === 'budget_alert') {
            store.addBudgetAlert(msg);
            store.addTranscript({
              id: `alert-${Date.now()}`,
              text: msg.message,
              speaker: 'shopper',
              confidence: 1,
              timestamp: Date.now(),
            });
          } else if (msg.type === 'substitution_suggestion') {
            store.addTranscript({
              id: `sub-${Date.now()}`,
              text: `⚠️ Substitution suggested for ${msg.original_item?.name}: ${msg.reason}`,
              speaker: 'shopper',
              confidence: 1,
              timestamp: Date.now(),
            });
          }
        } catch (e) {
          console.warn('[WS] Parse error', e);
        }
      };

      ws.onclose = () => {
        console.log('[WS] Customer disconnected');
        store.setConnectionState(false, 0);
        reconnectTimer = setTimeout(connect, 3000);
      };

      ws.onerror = () => ws?.close();
    };

    connect();

    // ── Video WebSocket: receive JPEG frames from shopper ──
    let videoWs: WebSocket | null = null;
    let videoReconnectTimer: ReturnType<typeof setTimeout>;
    let prevBlobUrl: string | null = null;

    const connectVideo = () => {
      const videoUrl = `${VIDEO_WS_BASE}/${SESSION_ID}?role=customer`;
      console.log('[VideoWS] Customer connecting to', videoUrl);
      videoWs = new WebSocket(videoUrl);
      videoWs.binaryType = 'arraybuffer';

      videoWs.onopen = () => {
        console.log('[VideoWS] Customer connected ✅');
      };

      videoWs.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
          // Write directly to <img> DOM element – bypasses React rendering
          // for smooth, zero-overhead frame updates
          if (prevBlobUrl) URL.revokeObjectURL(prevBlobUrl);
          const blob = new Blob([event.data], { type: 'image/jpeg' });
          const url = URL.createObjectURL(blob);
          prevBlobUrl = url;
          // Keep the latest frame as Blob for inspection
          lastFrameBlobRef.current = blob;
          if (imgRef.current) {
            imgRef.current.src = url;
          }
          // Only trigger one React render to flip the placeholder away
          if (!hasVideoFeedRef.current) {
            hasVideoFeedRef.current = true;
            setHasVideoFeed(true);
          }
        }
      };

      videoWs.onclose = () => {
        console.log('[VideoWS] Customer disconnected');
        videoReconnectTimer = setTimeout(connectVideo, 3000);
      };

      videoWs.onerror = () => videoWs?.close();
    };

    connectVideo();

    return () => {
      clearTimeout(reconnectTimer);
      ws?.close();
      clearTimeout(videoReconnectTimer);
      videoWs?.close();
      if (prevBlobUrl) URL.revokeObjectURL(prevBlobUrl);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Voice recording (Speech-to-Text via Web Speech API) ──
  const startRecording = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      console.warn('[STT] SpeechRecognition not supported in this browser');
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = 'en-US';
    recognition.interimResults = true;
    recognition.continuous = true;
    recognition.onresult = (event: any) => {
      let transcript = '';
      for (let i = 0; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      setRecordedText(transcript);
    };
    recognition.onerror = (e: any) => console.warn('[STT] Error:', e.error);
    recognition.onend = () => setIsRecording(false);
    recognitionRef.current = recognition;
    recognition.start();
    setIsRecording(true);
    setRecordedText('');
  };

  const stopRecording = () => {
    recognitionRef.current?.stop();
    setIsRecording(false);
  };

  // ── Send voice prompt to shopper (always as text → TTS on phone) ──
  const handleSendPrompt = () => {
    const ws = stateWsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.warn('[VoicePrompt] WS not connected');
      return;
    }

    // Prefer recorded speech text, fall back to typed text
    const text = (recordedText || promptText).trim();
    if (!text) return;

    ws.send(JSON.stringify({ type: 'voice_prompt', text }));
    console.log('[VoicePrompt] Sent text:', text);
    setPromptText('');
    setRecordedText('');
  };

  // ── Add / Remove items from shopping list ──
  const handleAddItem = () => {
    const name = newItemName.trim();
    if (!name) return;
    const price = parseFloat(newItemPrice) || 0;
    const ws = stateWsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'add_item',
        item_id: `cust-${Date.now()}`,
        name,
        unit_price: price,
        quantity_requested: 1,
      }));
      setNewItemName('');
      setNewItemPrice('');
    }
  };

  const handleRemoveItem = (itemId: string) => {
    const ws = stateWsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'remove_item', item_id: itemId }));
    }
  };

  // ── Click-to-Inspect: capture current frame → send to Grok Vision backend ──
  const handleInspectClick = async () => {
    if (isInspecting) return;
    if (!lastFrameBlobRef.current) {
      console.warn('[Inspect] No frame available yet');
      return;
    }

    setIsInspecting(true);
    setInspectionResult(null);

    try {
      const formData = new FormData();
      formData.append('image', lastFrameBlobRef.current, 'frame.jpg');

      const resp = await fetch(`/api/inspect/${SESSION_ID}`, {
        method: 'POST',
        body: formData,
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      console.log('[Inspect] Result:', data);
      setInspectionResult(data);

      // Auto-dismiss after 8 seconds
      setTimeout(() => setInspectionResult(null), 8000);
    } catch (err) {
      console.error('[Inspect] Error:', err);
      setInspectionResult({ error: 'Inspection failed. Is the backend running?' });
      setTimeout(() => setInspectionResult(null), 4000);
    } finally {
      setIsInspecting(false);
    }
  };

  // Freshness color helper
  const getFreshnessColor = (score: number | null) => {
    if (score === null) return '#555';
    if (score >= 0.85) return '#00FF88';
    if (score >= 0.65) return '#FFD700';
    if (score >= 0.40) return '#FF8C00';
    return '#FF3333';
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'picked': return '✓';
      case 'found': return '👁';
      case 'not_found': return '✗';
      case 'substituted': return '↔';
      default: return '○';
    }
  };

  const budgetColor =
    store.budgetPercent >= 100
      ? 'var(--color-danger)'
      : store.budgetPercent >= 90
      ? 'var(--color-warning)'
      : 'var(--color-success)';

  const pickedCount = store.cartItems.filter((i) => i.status === 'picked').length;
  const totalCount = store.cartItems.length;

  return (
    <div className="app-container">
      {/* ── Header ── */}
      <header className="header">
        <h1>🛒 VisionCart</h1>
        <div className="session-info">
          {store.session && (
            <>
              <span>Shopper: <strong>{store.session.shopperName}</strong></span>
              <span>|</span>
              <span>Room: {store.session.signalingRoom}</span>
              <span>|</span>
              <div className="status-dot" style={{
                background: store.isConnected ? 'var(--color-success)' : 'var(--color-danger)',
              }} />
              <span>{store.isConnected ? 'Live' : 'Disconnected'}</span>
            </>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginLeft: 'auto' }}>
          {store.customer && (
            <span style={{ fontSize: '13px', color: 'var(--color-text-secondary)' }}>
              👤 {store.customer.username}
            </span>
          )}
          <button
            onClick={() => store.logout()}
            style={{
              padding: '6px 14px',
              background: 'transparent',
              border: '1px solid var(--color-danger)',
              color: 'var(--color-danger)',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '13px',
              fontWeight: 600,
              transition: 'background 0.2s',
            }}
            onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,51,51,0.15)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          >
            Logout
          </button>
        </div>
      </header>

      {/* ── Video Panel ── */}
      <div className="video-panel" onClick={handleInspectClick} style={{ cursor: hasVideoFeed ? 'crosshair' : 'default', position: 'relative' }}>
        {/* img.src is updated directly via ref – not through React state */}
        <img
          ref={imgRef}
          alt="Shopper live feed"
          style={{
            background: '#111',
            width: '100%',
            height: '100%',
            objectFit: 'contain',
            display: hasVideoFeed ? 'block' : 'none',
          }}
        />
        {!hasVideoFeed && (
          <div style={{
            background: '#111',
            width: '100%',
            height: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#555',
            fontSize: '24px',
            fontFamily: 'sans-serif',
          }}>
            Waiting for shopper video feed…
          </div>
        )}
        {/* Inspection spinner */}
        {isInspecting && (
          <div style={{
            position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
            background: 'rgba(0,0,0,0.8)', borderRadius: '16px', padding: '20px 32px',
            color: '#00D4FF', fontSize: '16px', fontWeight: 600, zIndex: 20,
            display: 'flex', alignItems: 'center', gap: '12px',
          }}>
            <span style={{ animation: 'spin 1s linear infinite', display: 'inline-block' }}>⚠️</span>
            Analyzing with Grok Vision…
          </div>
        )}

        {/* Inspection result overlay */}
        {inspectionResult && !inspectionResult.error && (
          <div style={{
            position: 'absolute', bottom: '80px', left: '16px', right: '16px',
            background: 'rgba(0,0,0,0.9)', borderRadius: '12px', padding: '16px',
            color: '#e0e0e0', fontSize: '14px', zIndex: 20,
            border: `2px solid ${inspectionResult.score !== undefined
              ? (inspectionResult.score >= 0.65 ? '#00FF88' : inspectionResult.score >= 0.4 ? '#FFD700' : '#FF3333')
              : '#555'}`,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
              <strong>🔍 Quality Inspection</strong>
              <span style={{ color: '#888' }}>{inspectionResult.inference_ms}ms · {inspectionResult.model}</span>
            </div>
            {inspectionResult.item === 'unknown' ? (
              <div style={{ color: '#888' }}>No clear grocery item detected. Try clicking when a product is visible.</div>
            ) : (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
                  <span style={{ fontWeight: 700, fontSize: '16px', textTransform: 'capitalize' }}>
                    {inspectionResult.item}
                  </span>
                  <span style={{
                    color: inspectionResult.score >= 0.65 ? '#00FF88' : inspectionResult.score >= 0.4 ? '#FFD700' : '#FF3333',
                    fontWeight: 700,
                  }}>
                    {(inspectionResult.score * 100).toFixed(0)}% – {inspectionResult.grade}
                  </span>
                  {inspectionResult.is_bruised && (
                    <span style={{ color: '#FF8C00', fontWeight: 600 }}>⚠️ Bruised</span>
                  )}
                </div>
                {inspectionResult.details && (
                  <div style={{ color: '#aaa', fontSize: '12px', marginBottom: '6px' }}>
                    {inspectionResult.details}
                  </div>
                )}
                <div style={{
                  padding: '8px 12px', borderRadius: '8px',
                  background: inspectionResult.score < 0.65 ? 'rgba(255,51,51,0.2)' : 'rgba(0,255,136,0.1)',
                  fontSize: '13px',
                }}>
                  {inspectionResult.recommendation}
                  {inspectionResult.quality_alert_sent && (
                    <span style={{ color: '#00D4FF', marginLeft: '8px' }}>✉️ Alert sent to shopper</span>
                  )}
                </div>
              </>
            )}
          </div>
        )}

        {inspectionResult?.error && (
          <div style={{
            position: 'absolute', bottom: '80px', left: '16px', right: '16px',
            background: 'rgba(255,51,51,0.9)', borderRadius: '12px', padding: '16px',
            color: '#fff', fontSize: '14px', zIndex: 20,
          }}>
            {inspectionResult.error}
          </div>
        )}

        {/* Click hint */}
        {hasVideoFeed && !isInspecting && !inspectionResult && (
          <div style={{
            position: 'absolute', bottom: '80px', left: '50%', transform: 'translateX(-50%)',
            background: 'rgba(0,0,0,0.7)', borderRadius: '20px', padding: '6px 16px',
            color: '#aaa', fontSize: '12px', zIndex: 15, whiteSpace: 'nowrap',
          }}>
            🔍 Click anywhere to inspect quality with Grok Vision
          </div>
        )}

        {/* Connection badge */}
        <div className="video-overlay-badge">
          <div
            className="status-dot"
            style={{
              background: store.isConnected ? '#00FF88' : '#FF3333',
              animation: store.isConnected ? 'pulse 2s infinite' : 'none',
            }}
          />
          {store.isConnected ? 'LIVE' : 'CONNECTING...'}
        </div>

        {/* Latency badge */}
        <div className="latency-badge">
          {store.latencyMs}ms | {pickedCount}/{totalCount} items
        </div>
      </div>

      {/* ── Sidebar ── */}
      <div className="sidebar">
        {/* Budget Section */}
        <div className="sidebar-section">
          <h3>💰 Budget Tracker</h3>
          <div className="budget-bar">
            <div
              className="budget-bar-fill"
              style={{
                width: `${Math.min(100, store.budgetPercent)}%`,
                backgroundColor: budgetColor,
              }}
            />
          </div>
          <div className="budget-info">
            <span>${store.currentTotal.toFixed(2)} / ${store.budgetLimit.toFixed(2)}</span>
            <span style={{ color: budgetColor }}>{store.budgetPercent.toFixed(0)}%</span>
          </div>
          <div className="budget-info" style={{ color: 'var(--color-text-muted)', fontSize: '12px' }}>
            <span>Remaining: ${(store.budgetLimit - store.currentTotal).toFixed(2)}</span>
          </div>
        </div>

        {/* Shopping List */}
        <div className="sidebar-section" style={{ flex: 0 }}>
          <h3>📋 Shopping List ({pickedCount}/{totalCount})</h3>
        </div>
        <div className="shopping-list">
          {store.cartItems.map((item) => (
            <div
              key={item.itemId}
              className={`list-item ${item.status === 'picked' ? 'picked' : ''} ${
                item.freshnessScore !== null && item.freshnessScore < 0.65 ? 'flagged' : ''
              }`}
            >
              <span style={{ fontSize: '16px', width: '20px', textAlign: 'center' }}>
                {getStatusIcon(item.status)}
              </span>
              {item.freshnessScore !== null && (
                <div
                  className="freshness-dot"
                  style={{ backgroundColor: getFreshnessColor(item.freshnessScore) }}
                  title={`Freshness: ${(item.freshnessScore * 100).toFixed(0)}%`}
                />
              )}
              <div style={{ flex: 1 }}>
                <div>{item.name}</div>
                {item.freshnessScore !== null && (
                  <div style={{ fontSize: '11px', color: getFreshnessColor(item.freshnessScore) }}>
                    Freshness: {(item.freshnessScore * 100).toFixed(0)}% ({item.freshnessGrade})
                  </div>
                )}
              </div>
              <span className="item-price">
                ${(item.unitPrice * item.quantityRequested).toFixed(2)}
              </span>
              <button
                onClick={(e) => { e.stopPropagation(); handleRemoveItem(item.itemId); }}
                title="Remove item"
                style={{
                  background: 'rgba(255,51,51,0.2)', border: 'none', color: '#FF3333',
                  borderRadius: '6px', padding: '4px 8px', cursor: 'pointer',
                  fontSize: '12px', fontWeight: 700, marginLeft: '4px',
                }}
              >✕</button>
            </div>
          ))}
        </div>
        {/* Add Item */}
        <div style={{ padding: '8px 16px', display: 'flex', gap: '6px' }}>
          <input
            type="text"
            value={newItemName}
            onChange={(e) => setNewItemName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAddItem()}
            placeholder="Item name"
            style={{
              flex: 2, background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)',
              borderRadius: '6px', padding: '8px 10px', color: '#e0e0e0', fontSize: '13px', outline: 'none',
            }}
          />
          <input
            type="number"
            value={newItemPrice}
            onChange={(e) => setNewItemPrice(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAddItem()}
            placeholder="$"
            style={{
              flex: 0, width: '60px', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)',
              borderRadius: '6px', padding: '8px 10px', color: '#e0e0e0', fontSize: '13px', outline: 'none',
            }}
          />
          <button
            onClick={handleAddItem}
            disabled={!newItemName.trim()}
            style={{
              background: newItemName.trim() ? '#00FF88' : '#333', color: newItemName.trim() ? '#000' : '#666',
              border: 'none', borderRadius: '6px', padding: '8px 14px', fontWeight: 700, fontSize: '13px',
              cursor: newItemName.trim() ? 'pointer' : 'default', whiteSpace: 'nowrap',
            }}
          >+ Add</button>
        </div>

        {/* Voice Prompt to Shopper */}
        <div className="sidebar-section" style={{ flex: 0 }}>
          <h3>🔊 Talk to Shopper</h3>
        </div>
        <div style={{ padding: '0 16px 12px' }}>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <input
              type="text"
              value={recordedText || promptText}
              onChange={(e) => { setPromptText(e.target.value); setRecordedText(''); }}
              onKeyDown={(e) => e.key === 'Enter' && handleSendPrompt()}
              placeholder={isRecording ? '🎙 Listening…' : 'Type or record a message…'}
              readOnly={isRecording}
              style={{
                flex: 1,
                background: isRecording ? 'rgba(255,51,51,0.1)' : recordedText ? 'rgba(0,212,255,0.1)' : 'rgba(255,255,255,0.08)',
                border: `1px solid ${isRecording ? '#FF3333' : recordedText ? '#00D4FF' : 'rgba(255,255,255,0.15)'}`,
                borderRadius: '8px',
                padding: '10px 14px',
                color: '#e0e0e0',
                fontSize: '14px',
                outline: 'none',
              }}
            />
            {/* Record / Stop button */}
            <button
              onClick={isRecording ? stopRecording : startRecording}
              style={{
                background: isRecording ? '#FF3333' : 'rgba(255,255,255,0.1)',
                color: isRecording ? '#fff' : '#e0e0e0',
                border: isRecording ? '2px solid #FF3333' : '2px solid rgba(255,255,255,0.2)',
                borderRadius: '50%',
                width: '42px', height: '42px',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                cursor: 'pointer', fontSize: '18px', flexShrink: 0,
                animation: isRecording ? 'pulse 1s infinite' : 'none',
              }}
              title={isRecording ? 'Stop recording' : 'Record voice message'}
            >
              {isRecording ? '⏹' : '🎙'}
            </button>
            {/* Clear recorded text */}
            {recordedText && !isRecording && (
              <button
                onClick={() => setRecordedText('')}
                style={{
                  background: 'rgba(255,51,51,0.2)', border: 'none', color: '#FF3333',
                  borderRadius: '6px', padding: '8px', cursor: 'pointer', fontSize: '14px',
                }}
                title="Discard recording"
              >✕</button>
            )}
            <button
              onClick={handleSendPrompt}
              disabled={!promptText.trim() && !recordedText.trim()}
              style={{
                background: (promptText.trim() || recordedText.trim()) ? '#00D4FF' : '#333',
                color: (promptText.trim() || recordedText.trim()) ? '#000' : '#666',
                border: 'none',
                borderRadius: '8px',
                padding: '10px 18px',
                fontWeight: 700,
                fontSize: '14px',
                cursor: (promptText.trim() || recordedText.trim()) ? 'pointer' : 'default',
                whiteSpace: 'nowrap',
              }}
            >
              🔊 Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}


// ── App Wrapper with Auth ────────────────────────────────────────────────────

export default function App() {
  const { isLoggedIn, customer } = useStore();
  const [authChecked, setAuthChecked] = useState(true);

  // Toggle body scroll class based on auth state
  useEffect(() => {
    if (isLoggedIn) {
      document.body.classList.remove('auth-active');
      document.body.classList.add('portal-active');
    } else {
      document.body.classList.remove('portal-active');
      document.body.classList.add('auth-active');
    }
  }, [isLoggedIn]);

  if (!isLoggedIn) {
    return <AuthScreen onAuthSuccess={() => {}} />;
  }

  return <CustomerPortal />;
}