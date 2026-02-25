"""
VisionCart – Edge AI Pipeline Orchestrator

Coordinates the full CV pipeline for each video frame:
  1. Object Detection (YOLO)
  2. Freshness Analysis (for detected produce)
  3. Order Reconciliation (match against shopping list)
  4. Overlay Generation (annotations for AR display)

Runs at the edge (on the Shopper's device) for minimum latency.
Results are sent via WebRTC DataChannel to the Customer.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Set

import numpy as np

from app.ai import ObjectDetector
from app.ai.freshness import FreshnessDetector
from app.ai.reconciliation import OrderReconciler

logger = logging.getLogger("visioncart.pipeline")


# Produce categories eligible for freshness analysis
PRODUCE_CATEGORIES = {
    "apple", "banana", "orange", "grape", "strawberry", "lemon", "lime",
    "avocado", "tomato", "potato", "onion", "carrot", "broccoli",
    "lettuce", "pepper", "cucumber", "mushroom", "corn", "celery",
}


class VisionPipeline:
    """
    End-to-end vision processing pipeline for a single shopping session.

    Usage:
        pipeline = VisionPipeline(shopping_list=[...])
        pipeline.initialize()

        # Per frame:
        results = pipeline.process_frame(frame)
        # results contains detections, freshness, reconciliation, and overlays
    """

    def __init__(
        self,
        shopping_list: List[Dict] = None,
        model_path: str = "./ai-engine/models/yolov8n-grocery.pt",
        backend: str = "ultralytics",
        confidence: float = 0.5,
        freshness_threshold: float = 0.65,
    ):
        self.shopping_list = shopping_list or []
        self.picked_items: Set[str] = set()

        # Initialize sub-engines
        self.detector = ObjectDetector(
            model_path=model_path,
            backend=backend,
            confidence=confidence,
        )
        self.freshness = FreshnessDetector(bruise_threshold=freshness_threshold)
        self.reconciler = OrderReconciler()

        self._initialized = False
        self._frame_count = 0
        self._total_inference_ms = 0.0

    def initialize(self) -> None:
        """Load models. Call once before processing frames."""
        self.detector.load_model()
        self._initialized = True
        logger.info("Vision pipeline initialized")

    def process_frame(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        Process a single video frame through the full pipeline.

        Args:
            frame: BGR image (H, W, 3), uint8

        Returns:
            Dict with:
              - detections: raw object detection results
              - freshness_results: per-detection freshness analysis
              - reconciliation: shopping list match status
              - overlays: AR overlay annotations to render
              - timing: per-stage latency breakdown
        """
        if not self._initialized:
            self.initialize()

        self._frame_count += 1
        timings = {}
        t0 = time.perf_counter()

        # ── Stage 1: Object Detection ──
        t1 = time.perf_counter()
        detections = self.detector.detect(frame)
        timings["detection_ms"] = round((time.perf_counter() - t1) * 1000, 1)

        # ── Stage 2: Freshness Analysis (produce only) ──
        t2 = time.perf_counter()
        freshness_results = []
        for det in detections:
            if det["label"] in PRODUCE_CATEGORIES:
                # Crop ROI from frame
                roi = self._crop_roi(frame, det["bbox_pixels"])
                if roi is not None and roi.size > 0:
                    result = self.freshness.analyze(roi, det["label"])
                    result["detection_label"] = det["label"]
                    result["detection_confidence"] = det["confidence"]
                    freshness_results.append(result)
        timings["freshness_ms"] = round((time.perf_counter() - t2) * 1000, 1)

        # ── Stage 3: Order Reconciliation ──
        t3 = time.perf_counter()
        reconciliation = self.reconciler.reconcile(
            detections=detections,
            shopping_list=self.shopping_list,
            already_picked=self.picked_items,
        )
        timings["reconciliation_ms"] = round((time.perf_counter() - t3) * 1000, 1)

        # ── Stage 4: Generate Overlays ──
        t4 = time.perf_counter()
        overlays = self._generate_overlays(
            detections, freshness_results, reconciliation
        )
        timings["overlay_gen_ms"] = round((time.perf_counter() - t4) * 1000, 1)

        # ── Total timing ──
        total_ms = (time.perf_counter() - t0) * 1000
        timings["total_ms"] = round(total_ms, 1)
        self._total_inference_ms += total_ms

        return {
            "frame_number": self._frame_count,
            "detections": detections,
            "freshness_results": freshness_results,
            "reconciliation": reconciliation,
            "overlays": overlays,
            "timing": timings,
        }

    def mark_item_picked(self, item_id: str) -> None:
        """Mark a shopping list item as picked."""
        self.picked_items.add(item_id)

    def update_shopping_list(self, shopping_list: List[Dict]) -> None:
        """Update the shopping list (e.g., after substitution)."""
        self.shopping_list = shopping_list

    @property
    def avg_inference_ms(self) -> float:
        if self._frame_count == 0:
            return 0.0
        return self._total_inference_ms / self._frame_count

    def _crop_roi(
        self, frame: np.ndarray, bbox_pixels: List[int]
    ) -> Optional[np.ndarray]:
        """Crop a region of interest from the frame using pixel coordinates."""
        h, w = frame.shape[:2]
        x, y, bw, bh = bbox_pixels

        # Clamp to frame bounds
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(w, x + bw)
        y2 = min(h, y + bh)

        if x2 <= x1 or y2 <= y1:
            return None

        return frame[y1:y2, x1:x2].copy()

    def _generate_overlays(
        self,
        detections: List[Dict],
        freshness_results: List[Dict],
        reconciliation: Dict,
    ) -> List[Dict]:
        """
        Generate AR overlay annotations for rendering on the Shopper's screen.
        """
        overlays = []
        freshness_map = {
            fr["detection_label"]: fr for fr in freshness_results
        }

        for det in detections:
            label = det["label"]
            bbox = det["bbox"]
            conf = det["confidence"]

            # Base bounding box overlay
            color = "#00FF88"  # Green default
            annotation_text = f"{label} ({conf:.0%})"

            # Color code by freshness
            fr = freshness_map.get(label)
            if fr:
                score = fr["score"]
                if score >= 0.85:
                    color = "#00FF88"  # Green – excellent
                elif score >= 0.65:
                    color = "#FFD700"  # Gold – good
                elif score >= 0.40:
                    color = "#FF8C00"  # Orange – fair
                else:
                    color = "#FF3333"  # Red – poor
                annotation_text += f" | Fresh: {score:.0%}"

            # Check if this detection matches a list item
            is_on_list = any(
                m["detection"]["label"] == label
                for m in reconciliation.get("matches", [])
            )
            if is_on_list:
                annotation_text += " ✓ On List"

            overlays.append({
                "type": "detection_bbox",
                "x": bbox[0],
                "y": bbox[1],
                "width": bbox[2],
                "height": bbox[3],
                "color": color,
                "label": annotation_text,
                "freshness": fr["score"] if fr else None,
            })

        # Add progress overlay
        progress = reconciliation.get("progress", {})
        if progress:
            overlays.append({
                "type": "progress_badge",
                "text": (
                    f"🛒 {progress['picked']}/{progress['total_items']} "
                    f"({progress['completion_percent']}%)"
                ),
                "position": "top-right",
            })

        return overlays
