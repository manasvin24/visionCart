/**
 * VisionCart – WebRTC Hook
 *
 * Custom React hook encapsulating the full WebRTC peer connection lifecycle:
 *   1. Connect to signaling WebSocket
 *   2. Create RTCPeerConnection with ICE servers
 *   3. Exchange SDP offer/answer
 *   4. Trickle ICE candidates
 *   5. Attach remote video stream
 *   6. Open DataChannel for overlay and AI metadata
 *
 * Optimized for low-latency video reception:
 *   - Prefer VP8/H.264 hardware decode
 *   - Aggressive ICE candidate gathering
 *   - DataChannel with { ordered: false, maxRetransmits: 0 } for overlays
 */

import { useCallback, useEffect, useRef, useState } from 'react';

export interface WebRTCConfig {
  signalingUrl: string;
  roomId: string;
  role: 'shopper' | 'customer';
  iceServers?: RTCIceServer[];
}

export interface WebRTCState {
  connectionState: RTCPeerConnectionState | 'new';
  iceState: RTCIceConnectionState | 'new';
  signalingState: 'connecting' | 'connected' | 'disconnected' | 'error';
  remoteStream: MediaStream | null;
  dataChannel: RTCDataChannel | null;
  latencyMs: number;
}

const DEFAULT_ICE_SERVERS: RTCIceServer[] = [
  { urls: 'stun:stun.l.google.com:19302' },
  { urls: 'stun:stun1.l.google.com:19302' },
];

export function useWebRTC(config: WebRTCConfig) {
  const [state, setState] = useState<WebRTCState>({
    connectionState: 'new',
    iceState: 'new',
    signalingState: 'connecting',
    remoteStream: null,
    dataChannel: null,
    latencyMs: 0,
  });

  const pcRef = useRef<RTCPeerConnection | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const dcRef = useRef<RTCDataChannel | null>(null);
  const latencyIntervalRef = useRef<ReturnType<typeof setInterval>>();

  const onDataChannelMessage = useRef<((data: string) => void) | null>(null);

  const connect = useCallback(async () => {
    const { signalingUrl, roomId, role, iceServers } = config;

    // ── 1. Signaling WebSocket ──
    const wsUrl = `${signalingUrl}/signaling/${roomId}?role=${role}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    // ── 2. RTCPeerConnection ──
    const pc = new RTCPeerConnection({
      iceServers: iceServers || DEFAULT_ICE_SERVERS,
      iceCandidatePoolSize: 10,
    });
    pcRef.current = pc;

    // Track connection state
    pc.onconnectionstatechange = () => {
      setState((s) => ({ ...s, connectionState: pc.connectionState }));
    };

    pc.oniceconnectionstatechange = () => {
      setState((s) => ({ ...s, iceState: pc.iceConnectionState }));
    };

    // ── 3. Handle remote stream ──
    pc.ontrack = (event) => {
      const [stream] = event.streams;
      if (stream) {
        setState((s) => ({ ...s, remoteStream: stream }));
      }
    };

    // ── 4. ICE candidates → signaling server ──
    pc.onicecandidate = (event) => {
      if (event.candidate && ws.readyState === WebSocket.OPEN) {
        ws.send(
          JSON.stringify({
            type: 'ice-candidate',
            candidate: event.candidate.toJSON(),
          })
        );
      }
    };

    // ── 5. DataChannel (customer creates, shopper receives) ──
    if (role === 'customer') {
      const dc = pc.createDataChannel('visioncart-data', {
        ordered: false,
        maxRetransmits: 0, // Fire-and-forget for overlay coords
      });
      dcRef.current = dc;
      dc.onopen = () => setState((s) => ({ ...s, dataChannel: dc }));
      dc.onmessage = (e) => onDataChannelMessage.current?.(e.data);
    } else {
      pc.ondatachannel = (event) => {
        const dc = event.channel;
        dcRef.current = dc;
        dc.onopen = () => setState((s) => ({ ...s, dataChannel: dc }));
        dc.onmessage = (e) => onDataChannelMessage.current?.(e.data);
      };
    }

    // ── 6. Signaling message handler ──
    ws.onopen = () => {
      setState((s) => ({ ...s, signalingState: 'connected' }));
    };

    ws.onclose = () => {
      setState((s) => ({ ...s, signalingState: 'disconnected' }));
    };

    ws.onerror = () => {
      setState((s) => ({ ...s, signalingState: 'error' }));
    };

    ws.onmessage = async (event) => {
      const msg = JSON.parse(event.data);

      switch (msg.type) {
        case 'offer': {
          await pc.setRemoteDescription(new RTCSessionDescription({ type: 'offer', sdp: msg.sdp }));
          const answer = await pc.createAnswer();
          await pc.setLocalDescription(answer);
          ws.send(JSON.stringify({ type: 'answer', sdp: answer.sdp }));
          break;
        }

        case 'answer': {
          await pc.setRemoteDescription(new RTCSessionDescription({ type: 'answer', sdp: msg.sdp }));
          break;
        }

        case 'ice-candidate': {
          if (msg.candidate) {
            try {
              await pc.addIceCandidate(new RTCIceCandidate(msg.candidate));
            } catch (e) {
              console.warn('Failed to add ICE candidate:', e);
            }
          }
          break;
        }

        case 'peer-joined': {
          // If we're customer and shopper joined, create offer
          if (role === 'customer') {
            const offer = await pc.createOffer();
            await pc.setLocalDescription(offer);
            ws.send(JSON.stringify({ type: 'offer', sdp: offer.sdp }));
          }
          break;
        }

        case 'peer-left': {
          console.log(`Peer ${msg.role} left the session`);
          break;
        }

        case 'bye': {
          disconnect();
          break;
        }
      }
    };

    // ── 7. Latency measurement via DataChannel ping/pong ──
    latencyIntervalRef.current = setInterval(() => {
      if (dcRef.current?.readyState === 'open') {
        const pingTime = Date.now();
        dcRef.current.send(JSON.stringify({ type: 'ping', t: pingTime }));
      }
    }, 2000);
  }, [config]);

  const disconnect = useCallback(() => {
    if (latencyIntervalRef.current) {
      clearInterval(latencyIntervalRef.current);
    }
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'bye' }));
      wsRef.current.close();
    }
    pcRef.current?.close();

    setState({
      connectionState: 'new',
      iceState: 'new',
      signalingState: 'disconnected',
      remoteStream: null,
      dataChannel: null,
      latencyMs: 0,
    });
  }, []);

  const sendData = useCallback((data: Record<string, unknown>) => {
    if (dcRef.current?.readyState === 'open') {
      dcRef.current.send(JSON.stringify(data));
    }
  }, []);

  const setOnDataMessage = useCallback((handler: (data: string) => void) => {
    onDataChannelMessage.current = handler;
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return {
    state,
    connect,
    disconnect,
    sendData,
    setOnDataMessage,
    pc: pcRef,
  };
}
