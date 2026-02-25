/**
 * VisionCart – Canvas Overlay Hook
 *
 * Manages the interactive canvas overlay on the Customer's video feed:
 *   - Tap-to-highlight: Customer clicks/taps to create pulsing circles
 *   - AI detection boxes: Renders bounding boxes from the AI engine
 *   - Freshness badges: Color-coded freshness indicators
 *   - Text annotations: Labels and instructions
 *
 * All coordinates are normalized [0,1] for resolution-independent rendering.
 * Overlay events are sent to the Shopper via WebSocket for AR rendering.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

export interface OverlayItem {
  id: string;
  type: 'circle_pulse' | 'bbox' | 'text' | 'arrow' | 'progress_badge';
  x: number;
  y: number;
  width?: number;
  height?: number;
  radius?: number;
  color: string;
  label?: string;
  text?: string;
  durationMs: number;
  createdAt: number;
  fromX?: number;
  fromY?: number;
  toX?: number;
  toY?: number;
}

interface UseCanvasOverlayOptions {
  canvasRef: React.RefObject<HTMLCanvasElement>;
  videoRef: React.RefObject<HTMLVideoElement>;
  onTap?: (x: number, y: number) => void;
}

let overlayIdCounter = 0;

export function useCanvasOverlay({
  canvasRef,
  videoRef,
  onTap,
}: UseCanvasOverlayOptions) {
  const [overlays, setOverlays] = useState<OverlayItem[]>([]);
  const animFrameRef = useRef<number>(0);
  const overlaysRef = useRef<OverlayItem[]>([]);

  // Keep ref in sync with state for animation loop
  useEffect(() => {
    overlaysRef.current = overlays;
  }, [overlays]);

  /**
   * Convert a mouse/touch event to normalized [0,1] coordinates
   * relative to the video display area (accounting for letterboxing).
   */
  const eventToNormalized = useCallback(
    (clientX: number, clientY: number) => {
      const canvas = canvasRef.current;
      if (!canvas) return null;

      const rect = canvas.getBoundingClientRect();
      const x = (clientX - rect.left) / rect.width;
      const y = (clientY - rect.top) / rect.height;

      return {
        x: Math.max(0, Math.min(1, x)),
        y: Math.max(0, Math.min(1, y)),
      };
    },
    [canvasRef]
  );

  /**
   * Handle canvas click → create tap highlight + notify parent
   */
  const handleCanvasClick = useCallback(
    (e: MouseEvent) => {
      const coords = eventToNormalized(e.clientX, e.clientY);
      if (!coords) return;

      const highlight: OverlayItem = {
        id: `tap-${++overlayIdCounter}`,
        type: 'circle_pulse',
        x: coords.x,
        y: coords.y,
        radius: 25,
        color: '#FF6B35',
        durationMs: 3000,
        createdAt: Date.now(),
      };

      setOverlays((prev) => [...prev, highlight]);
      onTap?.(coords.x, coords.y);
    },
    [eventToNormalized, onTap]
  );

  /**
   * Add an AI detection overlay (bounding box + label)
   */
  const addDetection = useCallback(
    (detection: {
      x: number;
      y: number;
      width: number;
      height: number;
      label: string;
      color?: string;
      freshness?: number;
    }) => {
      const item: OverlayItem = {
        id: `det-${++overlayIdCounter}`,
        type: 'bbox',
        x: detection.x,
        y: detection.y,
        width: detection.width,
        height: detection.height,
        color: detection.color || '#00FF88',
        label: detection.label,
        durationMs: 2000,
        createdAt: Date.now(),
      };
      setOverlays((prev) => [...prev, item]);
    },
    []
  );

  /**
   * Add a text annotation
   */
  const addText = useCallback(
    (x: number, y: number, text: string, color = '#FFFFFF') => {
      const item: OverlayItem = {
        id: `txt-${++overlayIdCounter}`,
        type: 'text',
        x,
        y,
        color,
        text,
        durationMs: 5000,
        createdAt: Date.now(),
      };
      setOverlays((prev) => [...prev, item]);
    },
    []
  );

  /**
   * Clear all overlays
   */
  const clearOverlays = useCallback(() => {
    setOverlays([]);
  }, []);

  /**
   * Animation loop – renders all active overlays on the canvas
   */
  const renderLoop = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) {
      animFrameRef.current = requestAnimationFrame(renderLoop);
      return;
    }

    // Match canvas pixel size to display size
    const dpr = window.devicePixelRatio || 1;
    const displayW = canvas.clientWidth;
    const displayH = canvas.clientHeight;
    if (canvas.width !== displayW * dpr || canvas.height !== displayH * dpr) {
      canvas.width = displayW * dpr;
      canvas.height = displayH * dpr;
      ctx.scale(dpr, dpr);
    }

    ctx.clearRect(0, 0, displayW, displayH);

    const now = Date.now();
    const active = overlaysRef.current.filter(
      (o) => now - o.createdAt < o.durationMs
    );

    for (const item of active) {
      const elapsed = now - item.createdAt;
      const progress = elapsed / item.durationMs;
      const alpha = 1 - progress; // Fade out
      const px = item.x * displayW;
      const py = item.y * displayH;

      ctx.save();
      ctx.globalAlpha = Math.max(0.1, alpha);

      switch (item.type) {
        case 'circle_pulse': {
          const radius = (item.radius || 25) * (1 + progress * 0.5);
          ctx.strokeStyle = item.color;
          ctx.lineWidth = 3;
          ctx.beginPath();
          ctx.arc(px, py, radius, 0, Math.PI * 2);
          ctx.stroke();

          // Inner dot
          ctx.fillStyle = item.color;
          ctx.globalAlpha = Math.max(0.3, alpha * 0.6);
          ctx.beginPath();
          ctx.arc(px, py, 5, 0, Math.PI * 2);
          ctx.fill();
          break;
        }

        case 'bbox': {
          const bw = (item.width || 0.1) * displayW;
          const bh = (item.height || 0.1) * displayH;

          // Box
          ctx.strokeStyle = item.color;
          ctx.lineWidth = 2;
          ctx.setLineDash([6, 3]);
          ctx.strokeRect(px, py, bw, bh);
          ctx.setLineDash([]);

          // Corner accents
          const cornerLen = Math.min(15, bw * 0.2, bh * 0.2);
          ctx.lineWidth = 3;
          // Top-left
          ctx.beginPath();
          ctx.moveTo(px, py + cornerLen);
          ctx.lineTo(px, py);
          ctx.lineTo(px + cornerLen, py);
          ctx.stroke();
          // Top-right
          ctx.beginPath();
          ctx.moveTo(px + bw - cornerLen, py);
          ctx.lineTo(px + bw, py);
          ctx.lineTo(px + bw, py + cornerLen);
          ctx.stroke();
          // Bottom-left
          ctx.beginPath();
          ctx.moveTo(px, py + bh - cornerLen);
          ctx.lineTo(px, py + bh);
          ctx.lineTo(px + cornerLen, py + bh);
          ctx.stroke();
          // Bottom-right
          ctx.beginPath();
          ctx.moveTo(px + bw - cornerLen, py + bh);
          ctx.lineTo(px + bw, py + bh);
          ctx.lineTo(px + bw, py + bh - cornerLen);
          ctx.stroke();

          // Label
          if (item.label) {
            ctx.font = '12px -apple-system, sans-serif';
            const textW = ctx.measureText(item.label).width;
            ctx.fillStyle = item.color;
            ctx.globalAlpha = 0.85;
            ctx.fillRect(px, py - 20, textW + 12, 20);
            ctx.fillStyle = '#000';
            ctx.fillText(item.label, px + 6, py - 5);
          }
          break;
        }

        case 'text': {
          if (!item.text) break;
          ctx.font = 'bold 14px -apple-system, sans-serif';
          const textWidth = ctx.measureText(item.text).width;
          ctx.fillStyle = 'rgba(0,0,0,0.7)';
          ctx.fillRect(px - 4, py - 16, textWidth + 8, 22);
          ctx.fillStyle = item.color;
          ctx.fillText(item.text, px, py);
          break;
        }

        case 'arrow': {
          if (item.fromX == null || item.fromY == null || item.toX == null || item.toY == null) break;
          const fx = item.fromX * displayW;
          const fy = item.fromY * displayH;
          const tx = item.toX * displayW;
          const ty = item.toY * displayH;

          ctx.strokeStyle = item.color;
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(fx, fy);
          ctx.lineTo(tx, ty);
          ctx.stroke();

          // Arrowhead
          const angle = Math.atan2(ty - fy, tx - fx);
          const headLen = 12;
          ctx.beginPath();
          ctx.moveTo(tx, ty);
          ctx.lineTo(
            tx - headLen * Math.cos(angle - Math.PI / 6),
            ty - headLen * Math.sin(angle - Math.PI / 6)
          );
          ctx.moveTo(tx, ty);
          ctx.lineTo(
            tx - headLen * Math.cos(angle + Math.PI / 6),
            ty - headLen * Math.sin(angle + Math.PI / 6)
          );
          ctx.stroke();
          break;
        }
      }

      ctx.restore();
    }

    // Garbage collect expired overlays
    if (active.length !== overlaysRef.current.length) {
      setOverlays(active);
    }

    animFrameRef.current = requestAnimationFrame(renderLoop);
  }, [canvasRef]);

  // Start animation loop and attach click handler
  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas) {
      canvas.addEventListener('click', handleCanvasClick);
    }
    animFrameRef.current = requestAnimationFrame(renderLoop);

    return () => {
      if (canvas) {
        canvas.removeEventListener('click', handleCanvasClick);
      }
      cancelAnimationFrame(animFrameRef.current);
    };
  }, [canvasRef, handleCanvasClick, renderLoop]);

  return {
    overlays,
    addDetection,
    addText,
    clearOverlays,
  };
}
