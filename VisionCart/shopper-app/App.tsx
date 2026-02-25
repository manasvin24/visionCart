/**
 * VisionCart – Shopper App (Expo)
 *
 * Live camera + WebSocket sync to backend so Customer Portal sees updates.
 * Captures camera frames and sends them to the video relay for live viewing.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  FlatList,
  Animated,
  Dimensions,
  StatusBar,
  Platform,
} from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as Speech from 'expo-speech';
import { Audio } from 'expo-av';

// ═══════════════════════════════════════════════════════════════════════════════
// CONFIG – Your Mac's LAN IP (shown in Expo start output)
// ═══════════════════════════════════════════════════════════════════════════════
const BACKEND_HOST = '172.20.10.11:8000';
const BACKEND_WS = `ws://${BACKEND_HOST}/ws/state`;
const VIDEO_WS = `ws://${BACKEND_HOST}/ws/video`;
const SESSION_ID = 'demo-session';
// ═══════════════════════════════════════════════════════════════════════════════

interface ShoppingItem {
  id: string;
  name: string;
  unitPrice: number;
  status: 'pending' | 'found' | 'picked' | 'not_found';
  freshnessScore: number | null;
}

interface VoiceNotification {
  id: string;
  text: string;
  timestamp: number;
}

const { width: SCREEN_W, height: SCREEN_H } = Dimensions.get('window');

const COLORS = {
  primary: '#FF6B35',
  secondary: '#00D4FF',
  success: '#00FF88',
  warning: '#FFD700',
  danger: '#FF3333',
  bgDark: '#0a0a0f',
  text: '#e0e0e0',
  textMuted: '#888',
};

const INITIAL_ITEMS: ShoppingItem[] = [
  { id: '1', name: 'Organic Bananas', unitPrice: 1.29, status: 'pending', freshnessScore: null },
  { id: '2', name: 'Fuji Apples (3 ct)', unitPrice: 4.99, status: 'pending', freshnessScore: null },
  { id: '3', name: 'Avocados (2 ct)', unitPrice: 3.49, status: 'pending', freshnessScore: null },
  { id: '4', name: 'Whole Milk 1 gal', unitPrice: 4.29, status: 'pending', freshnessScore: null },
  { id: '5', name: 'Sourdough Bread', unitPrice: 5.49, status: 'pending', freshnessScore: null },
  { id: '6', name: 'Greek Yogurt (x2)', unitPrice: 1.79, status: 'pending', freshnessScore: null },
  { id: '7', name: 'Baby Spinach 5oz', unitPrice: 3.99, status: 'pending', freshnessScore: null },
  { id: '8', name: 'Cherry Tomatoes', unitPrice: 2.99, status: 'pending', freshnessScore: null },
];

// ── Voice Toast ──────────────────────────────────────────────────────────────

const VoiceToast: React.FC<{ notification: VoiceNotification }> = ({ notification }) => {
  const slideAnim = useRef(new Animated.Value(-100)).current;
  const opacityAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.spring(slideAnim, { toValue: 0, useNativeDriver: true }),
      Animated.timing(opacityAnim, { toValue: 1, duration: 300, useNativeDriver: true }),
    ]).start();
    const timer = setTimeout(() => {
      Animated.parallel([
        Animated.timing(slideAnim, { toValue: -100, duration: 300, useNativeDriver: true }),
        Animated.timing(opacityAnim, { toValue: 0, duration: 300, useNativeDriver: true }),
      ]).start();
    }, 5000);
    return () => clearTimeout(timer);
  }, []);

  return (
    <Animated.View style={[styles.voiceToast, { opacity: opacityAnim, transform: [{ translateY: slideAnim }] }]}>
      <Text style={styles.voiceToastIcon}>🎤</Text>
      <Text style={styles.voiceToastText} numberOfLines={2}>{notification.text}</Text>
    </Animated.View>
  );
};

// ── Main App ─────────────────────────────────────────────────────────────────

const ShopperApp: React.FC = () => {
  const [permission, requestPermission] = useCameraPermissions();
  const [items, setItems] = useState<ShoppingItem[]>(INITIAL_ITEMS);
  const [isConnected, setIsConnected] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [notifications, setNotifications] = useState<VoiceNotification[]>([]);
  const [qualityAlert, setQualityAlert] = useState<any>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const videoWsRef = useRef<WebSocket | null>(null);
  const cameraRef = useRef<CameraView>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();
  const frameIntervalRef = useRef<ReturnType<typeof setInterval>>();

  const pickedCount = items.filter((i) => i.status === 'picked').length;
  const currentTotal = items
    .filter((i) => i.status === 'picked')
    .reduce((sum, i) => sum + i.unitPrice, 0);
  const budgetLimit = 50.0;

  // ── Video frame capture & send ─────────────────────────────────────────────

  const connectVideoWs = useCallback(() => {
    const url = `${VIDEO_WS}/${SESSION_ID}?role=shopper`;
    console.log('[VideoWS] Connecting to', url);
    const ws = new WebSocket(url);

    ws.onopen = () => {
      console.log('[VideoWS] Connected ✅ – starting frame capture');
      setIsStreaming(true);
      videoWsRef.current = ws;

      let running = true;
      let isCapturing = false; // mutex: never overlap captures

      const captureLoop = async () => {
        while (running) {
          // Skip if WS not ready or a capture is already in flight
          if (ws.readyState !== WebSocket.OPEN || isCapturing || !cameraRef.current) {
            await new Promise((r) => setTimeout(r, 16));
            continue;
          }

          isCapturing = true;
          try {
            const photo = await cameraRef.current.takePictureAsync({
              quality: 0.15,          // Slightly higher quality than before
              base64: true,
              skipProcessing: true,   // Skips EXIF/orientation — 3× faster
              exif: false,            // Skip EXIF metadata collection
              shutterSound: false,
            } as any);                // `exif` flag not in all type defs yet

            if (photo?.base64 && ws.readyState === WebSocket.OPEN) {
              ws.send(photo.base64);  // Send as base64 text — no costly binary conversion
            }
          } catch (_) {
            // Camera busy / not ready — skip frame silently
          } finally {
            isCapturing = false;
          }

          // Yield to JS thread before next capture (~30 FPS target)
          await new Promise((r) => setTimeout(r, 33));
        }
      };

      captureLoop();
      (ws as any)._stopCapture = () => { running = false; };
    };

    ws.onclose = () => {
      console.log('[VideoWS] Disconnected');
      setIsStreaming(false);
      (ws as any)._stopCapture?.();
      // Auto-reconnect
      setTimeout(() => connectVideoWs(), 3000);
    };

    ws.onerror = () => ws.close();
  }, []);

  // ── WebSocket connect ──────────────────────────────────────────────────────

  const connectWs = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const url = `${BACKEND_WS}/${SESSION_ID}?role=shopper`;
    console.log('[WS] Connecting to', url);
    const ws = new WebSocket(url);

    ws.onopen = () => {
      console.log('[WS] Connected ✅');
      setIsConnected(true);

      // Send init_cart so backend and customer portal both get the list
      ws.send(JSON.stringify({
        type: 'init_cart',
        order_id: 'demo-order',
        budget_limit: budgetLimit,
        currency: 'USD',
        items: INITIAL_ITEMS.map((i) => ({
          item_id: i.id,
          inventory_id: `inv-${i.id}`,
          name: i.name,
          quantity_requested: 1,
          unit_price: i.unitPrice,
        })),
      }));

      addNotification('Connected to customer session');
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'cart_state') {
          // Sync state from server (e.g. if customer makes changes)
          const serverItems: ShoppingItem[] = msg.items.map((si: any) => ({
            id: si.item_id,
            name: si.name,
            unitPrice: si.unit_price,
            status: si.status,
            freshnessScore: si.freshness_score,
          }));
          setItems(serverItems);
        } else if (msg.type === 'budget_alert') {
          addNotification(`⚠️ ${msg.message}`);
        } else if (msg.type === 'substitution_suggestion') {
          addNotification(`Substitution suggested for ${msg.original_item?.name}`);
        } else if (msg.type === 'quality_alert') {
          // Customer inspected the video with Grok Vision
          console.log('[WS] Received quality_alert:', JSON.stringify(msg));
          const emoji = msg.score < 0.65 ? '⚠️' : '✅';
          const label = `${emoji} ${msg.item?.toUpperCase()}: ${msg.grade} (${(msg.score * 100).toFixed(0)}%)`;
          addNotification(msg.recommendation || label);
          // Always show the prominent banner so shopper sees every inspection
          setQualityAlert(msg);
          setTimeout(() => setQualityAlert(null), 10000);
        } else if (msg.type === 'voice_prompt') {
          // Customer sent a text message → speak it out loud via TTS
          const text = msg.text || '';
          if (text) {
            console.log('[TTS] Speaking:', text);
            addNotification(`🔊 Customer: "${text}"`);
            Speech.speak(text, {
              language: 'en-US',
              pitch: 1.0,
              rate: 0.95,
              onDone: () => console.log('[TTS] Done speaking'),
              onError: (err: Error) => console.warn('[TTS] Error:', err),
            });
          }
        }
      } catch (e) {
        console.warn('[WS] Parse error', e);
      }
    };

    ws.onclose = () => {
      console.log('[WS] Disconnected');
      setIsConnected(false);
      wsRef.current = null;
      reconnectTimer.current = setTimeout(connectWs, 3000);
    };

    ws.onerror = (e) => {
      console.warn('[WS] Error', e);
      ws.close();
    };

    wsRef.current = ws;
  }, []);

  const addNotification = (text: string) => {
    setNotifications((prev) => [
      ...prev.slice(-3),
      { id: `n-${Date.now()}`, text, timestamp: Date.now() },
    ]);
  };

  useEffect(() => {
    // Force audio through main speaker (not earpiece) even when camera is active
    Audio.setAudioModeAsync({
      allowsRecordingIOS: false,
      playsInSilentModeIOS: true,
      staysActiveInBackground: false,
      shouldDuckAndroid: true,
      playThroughEarpieceAndroid: false,
    }).then(() => console.log('[Audio] Session configured for speaker output'))
      .catch((e: any) => console.warn('[Audio] Session setup error:', e));

    connectWs();
    connectVideoWs();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
      (videoWsRef.current as any)?._stopCapture?.();
      videoWsRef.current?.close();
    };
  }, [connectWs, connectVideoWs]);

  // ── Pick item → send over WebSocket ────────────────────────────────────────

  const handlePickItem = useCallback((itemId: string) => {
    const freshness = +(0.70 + Math.random() * 0.28).toFixed(2);

    // Optimistic local update
    setItems((prev) =>
      prev.map((item) =>
        item.id === itemId
          ? { ...item, status: 'picked' as const, freshnessScore: freshness }
          : item
      )
    );

    // Send to backend → backend broadcasts to customer portal
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'item_picked',
        item_id: itemId,
        freshness_score: freshness,
        freshness_details: { grade: freshness >= 0.85 ? 'excellent' : freshness >= 0.65 ? 'good' : 'fair' },
      }));
      console.log(`[WS] Sent item_picked: ${itemId} (freshness: ${freshness})`);
    }
  }, []);

  // ── Helpers ────────────────────────────────────────────────────────────────

  const getFreshnessColor = (score: number | null): string => {
    if (score === null) return COLORS.textMuted;
    if (score >= 0.85) return COLORS.success;
    if (score >= 0.65) return COLORS.warning;
    return COLORS.danger;
  };

  const getStatusIcon = (status: string): string => {
    switch (status) {
      case 'picked': return '✓';
      case 'found': return '👁';
      case 'not_found': return '✗';
      default: return '○';
    }
  };

  // ── Camera permission screen ───────────────────────────────────────────────

  if (!permission) {
    return <View style={styles.container} />;
  }

  if (!permission.granted) {
    return (
      <View style={[styles.container, { justifyContent: 'center', alignItems: 'center' }]}>
        <Text style={{ color: COLORS.text, fontSize: 18, marginBottom: 20, textAlign: 'center', paddingHorizontal: 30 }}>
          VisionCart needs camera access{'\n'}to show the live shopping feed
        </Text>
        <TouchableOpacity
          onPress={requestPermission}
          style={{ backgroundColor: COLORS.primary, paddingHorizontal: 32, paddingVertical: 14, borderRadius: 12 }}
        >
          <Text style={{ color: '#fff', fontSize: 16, fontWeight: '700' }}>Grant Camera Access</Text>
        </TouchableOpacity>
      </View>
    );
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" />

      {/* Live Camera */}
      <CameraView ref={cameraRef} style={styles.cameraView} facing="back" />

      {/* Voice Notifications */}
      <View style={styles.notificationsContainer}>
        {notifications.map((n) => (
          <VoiceToast key={n.id} notification={n} />
        ))}
      </View>

      {/* ── Quality Alert Banner (from customer's YOLOv8 inspection) ── */}
      {qualityAlert && (
        <View style={{
          position: 'absolute', top: SCREEN_H * 0.15, left: 16, right: 16, zIndex: 20,
          backgroundColor: qualityAlert.score >= 0.65
            ? 'rgba(0,180,80,0.95)'
            : qualityAlert.score >= 0.4
              ? 'rgba(255,165,0,0.95)'
              : 'rgba(255,51,51,0.95)',
          borderRadius: 16, padding: 16,
          shadowColor: '#000', shadowOffset: { width: 0, height: 4 },
          shadowOpacity: 0.5, shadowRadius: 8, elevation: 10,
        }}>
          <Text style={{ color: '#fff', fontSize: 18, fontWeight: '800', marginBottom: 4 }}>
            {qualityAlert.score >= 0.65 ? '✅' : '⚠️'} Quality Check from Customer
          </Text>
          <Text style={{ color: '#fff', fontSize: 15, fontWeight: '600', textTransform: 'capitalize' }}>
            {qualityAlert.item} — {qualityAlert.grade} ({(qualityAlert.score * 100).toFixed(0)}%)
          </Text>
          <Text style={{ color: 'rgba(255,255,255,0.9)', fontSize: 13, marginTop: 4 }}>
            {qualityAlert.recommendation}
          </Text>
          {qualityAlert.is_bruised && (
            <Text style={{ color: '#FFD700', fontSize: 13, fontWeight: '700', marginTop: 4 }}>
              🍎 Bruising detected — consider picking a different one
            </Text>
          )}
          <TouchableOpacity
            onPress={() => setQualityAlert(null)}
            style={{ position: 'absolute', top: 8, right: 12 }}
          >
            <Text style={{ color: 'rgba(255,255,255,0.7)', fontSize: 20 }}>✕</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Top HUD */}
      <View style={styles.topHud}>
        <View style={styles.hudBadge}>
          <View style={[styles.statusDot, { backgroundColor: isConnected ? COLORS.success : COLORS.danger }]} />
          <Text style={styles.hudText}>{isConnected ? 'LIVE' : 'OFFLINE'}</Text>
        </View>
        <View style={styles.hudBadge}>
          <Text style={styles.hudText}>🛒 {pickedCount}/{items.length}</Text>
        </View>
        <View style={styles.hudBadge}>
          <Text style={styles.hudText}>💰 ${currentTotal.toFixed(2)} / ${budgetLimit.toFixed(2)}</Text>
        </View>
        <View style={styles.hudBadge}>
          <View style={[styles.statusDot, { backgroundColor: isStreaming ? '#FF6B35' : COLORS.textMuted }]} />
          <Text style={styles.hudText}>{isStreaming ? '📹 STREAM' : '📹 OFF'}</Text>
        </View>
      </View>

      {/* Bottom Panel – Shopping List */}
      <View style={styles.bottomPanel}>
        <View style={styles.bottomPanelHeader}>
          <Text style={styles.bottomPanelTitle}>
            Next Items ({items.filter((i) => i.status === 'pending').length} remaining)
          </Text>
        </View>
        <FlatList
          data={items.filter((i) => i.status === 'pending' || i.status === 'found')}
          renderItem={({ item }) => (
            <TouchableOpacity
              style={[styles.listItem, item.status === 'picked' && styles.listItemPicked]}
              onPress={() => item.status !== 'picked' && handlePickItem(item.id)}
              activeOpacity={0.7}
            >
              <Text style={[styles.listItemIcon, { color: getFreshnessColor(item.freshnessScore) }]}>
                {getStatusIcon(item.status)}
              </Text>
              <View style={{ flex: 1 }}>
                <Text style={[styles.listItemName, item.status === 'picked' && { textDecorationLine: 'line-through', opacity: 0.6 }]}>
                  {item.name}
                </Text>
                {item.freshnessScore !== null && (
                  <Text style={{ fontSize: 10, color: getFreshnessColor(item.freshnessScore) }}>
                    Fresh: {(item.freshnessScore * 100).toFixed(0)}%
                  </Text>
                )}
              </View>
              <Text style={{ color: COLORS.textMuted, fontSize: 12 }}>${item.unitPrice.toFixed(2)}</Text>
            </TouchableOpacity>
          )}
          keyExtractor={(item) => item.id}
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ paddingHorizontal: 12 }}
        />
      </View>
    </View>
  );
};

// ── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bgDark },
  cameraView: { flex: 1 },
  notificationsContainer: { position: 'absolute', top: 100, left: 20, right: 20, zIndex: 10 },
  voiceToast: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: 'rgba(0,0,0,0.85)',
    borderRadius: 12, padding: 12, marginBottom: 8, borderLeftWidth: 4, borderLeftColor: COLORS.secondary,
  },
  voiceToastIcon: { fontSize: 20, marginRight: 10 },
  voiceToastText: { color: COLORS.text, fontSize: 14, flex: 1 },
  topHud: { position: 'absolute', top: 55, left: 0, right: 0, flexDirection: 'row', justifyContent: 'center', gap: 10, zIndex: 5 },
  hudBadge: { flexDirection: 'row', alignItems: 'center', backgroundColor: 'rgba(0,0,0,0.7)', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16, gap: 6 },
  hudText: { color: COLORS.text, fontSize: 12, fontWeight: '600' },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  bottomPanel: { position: 'absolute', bottom: 0, left: 0, right: 0, backgroundColor: 'rgba(0,0,0,0.85)', borderTopLeftRadius: 20, borderTopRightRadius: 20, paddingVertical: 14, paddingBottom: 34 },
  bottomPanelHeader: { paddingHorizontal: 16, marginBottom: 10 },
  bottomPanelTitle: { color: COLORS.text, fontSize: 14, fontWeight: '700' },
  listItem: { flexDirection: 'row', alignItems: 'center', backgroundColor: 'rgba(255,255,255,0.08)', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, marginRight: 8, minWidth: 150, gap: 8 },
  listItemPicked: { opacity: 0.5 },
  listItemIcon: { fontSize: 16, width: 20, textAlign: 'center' },
  listItemName: { color: COLORS.text, fontSize: 13, fontWeight: '500' },
});

export default ShopperApp;
