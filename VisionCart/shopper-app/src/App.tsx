/**
 * VisionCart – Shopper App Entry Point (React Native)
 *
 * The Shopper's POV camera app with:
 *   - Live camera stream broadcast via WebRTC
 *   - AR overlay rendering (customer taps, AI detections)
 *   - On-device AI inference for low-latency detection
 *   - Voice notification display from customer transcriptions
 *   - Shopping list progress HUD
 */

// Ambient declarations for timer globals (resolved by react-native types at build time)
declare function setTimeout(handler: () => void, timeout?: number): number;
declare function clearTimeout(id: number | undefined): void;

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
  Alert,
} from 'react-native';

// ── Types ────────────────────────────────────────────────────────────────────

interface OverlayItem {
  id: string;
  type: 'circle_pulse' | 'bbox' | 'text';
  x: number;          // Normalized [0, 1]
  y: number;          // Normalized [0, 1]
  width?: number;
  height?: number;
  radius?: number;
  color: string;
  label?: string;
  text?: string;
  durationMs: number;
  createdAt: number;
}

interface ShoppingItem {
  id: string;
  name: string;
  status: 'pending' | 'found' | 'picked' | 'not_found';
  freshnessScore: number | null;
}

interface VoiceNotification {
  id: string;
  text: string;
  timestamp: number;
}

// ── Constants ────────────────────────────────────────────────────────────────

const { width: SCREEN_W, height: SCREEN_H } = Dimensions.get('window');

const COLORS = {
  primary: '#FF6B35',
  secondary: '#00D4FF',
  success: '#00FF88',
  warning: '#FFD700',
  danger: '#FF3333',
  bgDark: '#0a0a0f',
  bgCard: 'rgba(0, 0, 0, 0.75)',
  text: '#e0e0e0',
  textMuted: '#888',
};

// ── Demo Data ────────────────────────────────────────────────────────────────

const DEMO_ITEMS: ShoppingItem[] = [
  { id: '1', name: 'Organic Bananas', status: 'picked', freshnessScore: 0.91 },
  { id: '2', name: 'Fuji Apples (3 ct)', status: 'picked', freshnessScore: 0.88 },
  { id: '3', name: 'Avocados (2 ct)', status: 'found', freshnessScore: null },
  { id: '4', name: 'Whole Milk 1 gal', status: 'pending', freshnessScore: null },
  { id: '5', name: 'Sourdough Bread', status: 'pending', freshnessScore: null },
  { id: '6', name: 'Greek Yogurt (x2)', status: 'pending', freshnessScore: null },
  { id: '7', name: 'Baby Spinach 5oz', status: 'not_found', freshnessScore: null },
  { id: '8', name: 'Cherry Tomatoes', status: 'pending', freshnessScore: null },
];

// ── Helper Components ────────────────────────────────────────────────────────

/** Pulsing circle overlay from customer tap */
const TapHighlight: React.FC<{ overlay: OverlayItem }> = ({ overlay }) => {
  const pulseAnim = useRef(new Animated.Value(1)).current;
  const opacityAnim = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, {
          toValue: 1.5,
          duration: 600,
          useNativeDriver: true,
        }),
        Animated.timing(pulseAnim, {
          toValue: 1,
          duration: 600,
          useNativeDriver: true,
        }),
      ])
    ).start();

    Animated.timing(opacityAnim, {
      toValue: 0,
      duration: overlay.durationMs,
      useNativeDriver: true,
    }).start();
  // pulseAnim and opacityAnim are stable Animated.Value refs
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overlay.durationMs]);

  const size = (overlay.radius || 25) * 2;
  return (
    <Animated.View
      style={{
        position: 'absolute',
        left: overlay.x * SCREEN_W - size / 2,
        top: overlay.y * SCREEN_H - size / 2,
        width: size,
        height: size,
        borderRadius: size / 2,
        borderWidth: 3,
        borderColor: overlay.color,
        opacity: opacityAnim,
        transform: [{ scale: pulseAnim }],
      }}
    >
      <View
        style={{
          position: 'absolute',
          top: size / 2 - 4,
          left: size / 2 - 4,
          width: 8,
          height: 8,
          borderRadius: 4,
          backgroundColor: overlay.color,
        }}
      />
    </Animated.View>
  );
};

/** Voice notification toast */
const VoiceToast: React.FC<{ notification: VoiceNotification }> = ({
  notification,
}) => {
  const slideAnim = useRef(new Animated.Value(-100)).current;
  const opacityAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.spring(slideAnim, { toValue: 0, useNativeDriver: true }),
      Animated.timing(opacityAnim, {
        toValue: 1,
        duration: 300,
        useNativeDriver: true,
      }),
    ]).start();

    // Auto-dismiss after 5s
    const timer = setTimeout(() => {
      Animated.parallel([
        Animated.timing(slideAnim, {
          toValue: -100,
          duration: 300,
          useNativeDriver: true,
        }),
        Animated.timing(opacityAnim, {
          toValue: 0,
          duration: 300,
          useNativeDriver: true,
        }),
      ]).start();
    }, 5000);
    return () => clearTimeout(timer);
  // slideAnim and opacityAnim are stable Animated.Value refs
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Animated.View
      style={[
        styles.voiceToast,
        {
          opacity: opacityAnim,
          transform: [{ translateY: slideAnim }],
        },
      ]}
    >
      <Text style={styles.voiceToastIcon}>🎤</Text>
      <Text style={styles.voiceToastText} numberOfLines={2}>
        {notification.text}
      </Text>
    </Animated.View>
  );
};

// ── Main App ─────────────────────────────────────────────────────────────────

const ShopperApp: React.FC = () => {
  const [isConnected, setIsConnected] = useState(true);
  const [overlays, setOverlays] = useState<OverlayItem[]>([]);
  const [items, setItems] = useState<ShoppingItem[]>(DEMO_ITEMS);
  const [notifications, setNotifications] = useState<VoiceNotification[]>([
    {
      id: 'n1',
      text: 'Can you check the avocados? Look for ones that are slightly firm.',
      timestamp: Date.now(),
    },
  ]);
  const [currentTotal, setCurrentTotal] = useState(6.18);
  const [budgetLimit] = useState(50.0);

  const pickedCount = items.filter((i: ShoppingItem) => i.status === 'picked').length;

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

  const handlePickItem = useCallback((itemId: string) => {
    setItems((prev: ShoppingItem[]) =>
      prev.map((item: ShoppingItem) =>
        item.id === itemId
          ? { ...item, status: 'picked' as const, freshnessScore: 0.82 + Math.random() * 0.15 }
          : item
      )
    );
    // In production: trigger AI freshness analysis + send via state sync WebSocket
  }, []);

  const renderListItem = useCallback(
    ({ item }: { item: ShoppingItem }) => (
      <TouchableOpacity
        style={[
          styles.listItem,
          item.status === 'picked' && styles.listItemPicked,
        ]}
        onPress={() => item.status !== 'picked' && handlePickItem(item.id)}
        activeOpacity={0.7}
      >
        <Text style={[styles.listItemIcon, { color: getFreshnessColor(item.freshnessScore) }]}>
          {getStatusIcon(item.status)}
        </Text>
        <View style={{ flex: 1 }}>
          <Text
            style={[
              styles.listItemName,
              item.status === 'picked' && { textDecorationLine: 'line-through', opacity: 0.6 },
            ]}
          >
            {item.name}
          </Text>
          {item.freshnessScore !== null && (
            <Text style={{ fontSize: 10, color: getFreshnessColor(item.freshnessScore) }}>
              Fresh: {(item.freshnessScore * 100).toFixed(0)}%
            </Text>
          )}
        </View>
      </TouchableOpacity>
    ),
    [handlePickItem]
  );

  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" />

      {/* Camera view placeholder (react-native-camera in production) */}
      <View style={styles.cameraView}>
        <Text style={styles.cameraPlaceholder}>📷 Live Camera Feed</Text>
        <Text style={styles.cameraSubtext}>
          (Connect react-native-camera + WebRTC stream)
        </Text>
      </View>

      {/* AR Overlays */}
      {overlays.map((overlay: OverlayItem) => (
        <TapHighlight key={overlay.id} overlay={overlay} />
      ))}

      {/* Voice Notifications */}
      <View style={styles.notificationsContainer}>
        {notifications.map((n: VoiceNotification) => (
          <VoiceToast key={n.id} notification={n} />
        ))}
      </View>

      {/* Top HUD – Status Bar */}
      <View style={styles.topHud}>
        <View style={styles.hudBadge}>
          <View
            style={[
              styles.statusDot,
              { backgroundColor: isConnected ? COLORS.success : COLORS.danger },
            ]}
          />
          <Text style={styles.hudText}>
            {isConnected ? 'LIVE' : 'OFFLINE'}
          </Text>
        </View>
        <View style={styles.hudBadge}>
          <Text style={styles.hudText}>
            🛒 {pickedCount}/{items.length}
          </Text>
        </View>
        <View style={styles.hudBadge}>
          <Text style={styles.hudText}>
            💰 ${currentTotal.toFixed(2)} / ${budgetLimit.toFixed(2)}
          </Text>
        </View>
      </View>

      {/* Bottom Panel – Mini Shopping List */}
      <View style={styles.bottomPanel}>
        <View style={styles.bottomPanelHeader}>
          <Text style={styles.bottomPanelTitle}>
            Next Items ({items.filter((i: ShoppingItem) => i.status === 'pending').length} remaining)
          </Text>
        </View>
        <FlatList
          data={items.filter(
            (i: ShoppingItem) => i.status === 'pending' || i.status === 'found'
          )}
          renderItem={renderListItem}
          keyExtractor={(item: ShoppingItem) => item.id}
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
  container: {
    flex: 1,
    backgroundColor: COLORS.bgDark,
  },
  cameraView: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#111',
  },
  cameraPlaceholder: {
    color: '#444',
    fontSize: 24,
    fontWeight: '700',
  },
  cameraSubtext: {
    color: '#333',
    fontSize: 13,
    marginTop: 8,
  },
  notificationsContainer: {
    position: 'absolute',
    top: 100,
    left: 20,
    right: 20,
    zIndex: 10,
  },
  voiceToast: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(0, 0, 0, 0.85)',
    borderRadius: 12,
    padding: 12,
    marginBottom: 8,
    borderLeftWidth: 4,
    borderLeftColor: COLORS.secondary,
  },
  voiceToastIcon: {
    fontSize: 20,
    marginRight: 10,
  },
  voiceToastText: {
    color: COLORS.text,
    fontSize: 14,
    flex: 1,
  },
  topHud: {
    position: 'absolute',
    top: 50,
    left: 0,
    right: 0,
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 10,
    zIndex: 5,
  },
  hudBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(0, 0, 0, 0.7)',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    gap: 6,
  },
  hudText: {
    color: COLORS.text,
    fontSize: 12,
    fontWeight: '600',
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  bottomPanel: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.85)',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    paddingVertical: 14,
    paddingBottom: 30, // Safe area
  },
  bottomPanelHeader: {
    paddingHorizontal: 16,
    marginBottom: 10,
  },
  bottomPanelTitle: {
    color: COLORS.text,
    fontSize: 14,
    fontWeight: '700',
  },
  listItem: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.08)',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginRight: 8,
    minWidth: 140,
    gap: 8,
  },
  listItemPicked: {
    opacity: 0.5,
  },
  listItemIcon: {
    fontSize: 16,
    width: 20,
    textAlign: 'center',
  },
  listItemName: {
    color: COLORS.text,
    fontSize: 13,
    fontWeight: '500',
  },
});

export default ShopperApp;
