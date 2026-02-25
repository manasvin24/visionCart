/**
 * VisionCart – Shopper Edge AI Service
 *
 * Bridge between React Native and the on-device AI inference engine.
 * In production, this uses TFLite via a native module for GPU-accelerated inference.
 *
 * Responsibilities:
 *   1. Capture frames from the camera stream
 *   2. Run YOLO detection + freshness analysis
 *   3. Perform order reconciliation
 *   4. Send results to the UI overlay and via DataChannel to the Customer
 *
 * Latency target: < 50ms per frame on modern mobile GPU.
 */

// ── Types ────────────────────────────────────────────────────────────────────

export interface Detection {
  label: string;
  confidence: number;
  bbox: [number, number, number, number]; // [x, y, w, h] normalized
  freshnessScore?: number;
  freshnessGrade?: string;
}

export interface FrameResult {
  frameNumber: number;
  detections: Detection[];
  reconciliation: {
    matches: Array<{ detectionLabel: string; itemId: string }>;
    progress: { picked: number; total: number; percent: number };
  };
  timingMs: number;
}

export interface ShoppingListItem {
  id: string;
  name: string;
  detectionLabels: string[];
  quantityRequested: number;
}

// ── Edge AI Service ──────────────────────────────────────────────────────────

class EdgeAIService {
  private isInitialized = false;
  private frameCount = 0;
  private shoppingList: ShoppingListItem[] = [];
  private pickedItemIds: Set<string> = new Set();

  /**
   * Initialize the on-device model.
   * In production: loads TFLite model via native module.
   */
  async initialize(modelPath?: string): Promise<void> {
    console.log('[EdgeAI] Initializing model...');
    // Production: NativeModules.TFLiteModule.loadModel(modelPath);
    this.isInitialized = true;
    console.log('[EdgeAI] Model ready');
  }

  /**
   * Set the shopping list for order reconciliation.
   */
  setShoppingList(items: ShoppingListItem[]): void {
    this.shoppingList = items;
  }

  /**
   * Mark an item as picked.
   */
  markItemPicked(itemId: string): void {
    this.pickedItemIds.add(itemId);
  }

  /**
   * Process a single camera frame.
   * In production: sends pixel data to TFLite native module.
   *
   * @param frameData - Base64 encoded frame or pixel buffer reference
   * @returns Detection results with freshness and reconciliation
   */
  async processFrame(frameData: string): Promise<FrameResult> {
    if (!this.isInitialized) {
      await this.initialize();
    }

    const startTime = performance.now();
    this.frameCount++;

    // ── Mock inference for MVP pipeline testing ──
    // Production: const rawDetections = await NativeModules.TFLiteModule.detect(frameData);

    const detections = this.mockDetections();
    const reconciliation = this.reconcile(detections);

    const timingMs = performance.now() - startTime;

    return {
      frameNumber: this.frameCount,
      detections,
      reconciliation,
      timingMs: Math.round(timingMs * 10) / 10,
    };
  }

  /**
   * Reconcile detections against the shopping list.
   */
  private reconcile(detections: Detection[]) {
    const matches: Array<{ detectionLabel: string; itemId: string }> = [];

    for (const det of detections) {
      for (const item of this.shoppingList) {
        if (this.pickedItemIds.has(item.id)) continue;

        const labelMatch = item.detectionLabels.some(
          (l) =>
            l.toLowerCase() === det.label.toLowerCase() ||
            det.label.toLowerCase().includes(l.toLowerCase())
        );

        if (labelMatch && det.confidence >= 0.7) {
          matches.push({
            detectionLabel: det.label,
            itemId: item.id,
          });
          break;
        }
      }
    }

    const picked = this.pickedItemIds.size + matches.length;
    const total = this.shoppingList.length;

    return {
      matches,
      progress: {
        picked,
        total,
        percent: total > 0 ? Math.round((picked / total) * 100) : 0,
      },
    };
  }

  /**
   * Generate mock detections for pipeline validation.
   * Replace with actual TFLite inference in production.
   */
  private mockDetections(): Detection[] {
    const labels = [
      'banana', 'apple', 'avocado', 'milk', 'bread',
      'tomato', 'orange', 'lettuce', 'yogurt', 'cheese',
    ];

    const numDetections = Math.floor(Math.random() * 3) + 1;
    const detections: Detection[] = [];

    for (let i = 0; i < numDetections; i++) {
      const label = labels[Math.floor(Math.random() * labels.length)];
      const conf = 0.55 + Math.random() * 0.43;
      const freshness = 0.3 + Math.random() * 0.7;

      detections.push({
        label,
        confidence: Math.round(conf * 1000) / 1000,
        bbox: [
          Math.random() * 0.6 + 0.1,
          Math.random() * 0.6 + 0.1,
          Math.random() * 0.15 + 0.05,
          Math.random() * 0.15 + 0.05,
        ],
        freshnessScore: Math.round(freshness * 1000) / 1000,
        freshnessGrade:
          freshness >= 0.85 ? 'excellent' :
          freshness >= 0.65 ? 'good' :
          freshness >= 0.4 ? 'fair' : 'poor',
      });
    }

    return detections;
  }

  /**
   * Get inference performance stats.
   */
  getStats() {
    return {
      framesProcessed: this.frameCount,
      isInitialized: this.isInitialized,
      shoppingListSize: this.shoppingList.length,
      pickedItems: this.pickedItemIds.size,
    };
  }
}

// Singleton export
export const edgeAI = new EdgeAIService();
