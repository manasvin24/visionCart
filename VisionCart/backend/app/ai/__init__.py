"""
VisionCart – AI Computer Vision Engine

Edge-optimized inference pipeline for:
  1. Object Detection (YOLO v8-nano) → Identify produce and packaging
  2. Freshness Heuristics → Color/texture analysis for bruising
  3. Order Reconciliation → Match detected items against shopping list

Design principles:
  - Target < 50ms total inference per frame on mobile GPU
  - Batch-free, single-frame processing for minimal latency
  - Fallback to CPU with quantized INT8 model
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("visioncart.ai")


# ── Object Detection ──────────────────────────────────────────────────────────


class ObjectDetector:
    """
    YOLO v8-nano based grocery item detector.

    In production, this loads a fine-tuned YOLO model trained on grocery datasets
    (Freiburg Groceries, MVTec, or custom). For the MVP framework, we provide
    the full inference pipeline with a pluggable model backend.

    Supported backends:
      - ultralytics (YOLO native)
      - onnxruntime (ONNX exported model)
      - tflite (TensorFlow Lite for mobile edge)
    """

    # Common grocery detection classes (subset of COCO + custom)
    GROCERY_CLASSES = [
        "apple", "banana", "orange", "grape", "strawberry", "lemon", "lime",
        "avocado", "tomato", "potato", "onion", "carrot", "broccoli",
        "lettuce", "pepper", "cucumber", "mushroom", "corn", "celery",
        "bread", "milk", "cheese", "yogurt", "egg_carton", "butter",
        "chicken", "beef", "fish", "cereal_box", "pasta", "rice",
        "canned_good", "bottle", "jar", "bag", "box", "package",
    ]

    def __init__(
        self,
        model_path: str = "./ai-engine/models/yolov8n-grocery.pt",
        backend: str = "ultralytics",
        confidence: float = 0.5,
        nms_threshold: float = 0.4,
        input_size: Tuple[int, int] = (416, 416),
        device: str = "auto",
    ):
        self.model_path = model_path
        self.backend = backend
        self.confidence = confidence
        self.nms_threshold = nms_threshold
        self.input_size = input_size
        self.device = device
        self._model = None

        logger.info(
            f"ObjectDetector initialized: backend={backend}, "
            f"input_size={input_size}, confidence={confidence}"
        )

    def load_model(self) -> None:
        """
        Load the detection model. Call once at startup.

        For MVP: if model file doesn't exist, operates in mock mode
        with synthetic detections for testing the pipeline.
        """
        model_file = Path(self.model_path)

        if not model_file.exists():
            logger.warning(
                f"Model not found at {self.model_path}. "
                "Running in mock mode for pipeline testing."
            )
            self._model = "mock"
            return

        if self.backend == "ultralytics":
            try:
                from ultralytics import YOLO
                self._model = YOLO(self.model_path)
                logger.info(f"YOLO model loaded from {self.model_path}")
            except ImportError:
                logger.error("ultralytics package not installed")
                self._model = "mock"

        elif self.backend == "onnxruntime":
            try:
                import onnxruntime as ort
                sess_options = ort.SessionOptions()
                sess_options.graph_optimization_level = (
                    ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                )
                providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
                self._model = ort.InferenceSession(
                    self.model_path, sess_options, providers=providers
                )
                logger.info(f"ONNX model loaded from {self.model_path}")
            except ImportError:
                logger.error("onnxruntime package not installed")
                self._model = "mock"

    def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Run object detection on a single video frame.

        Args:
            frame: BGR image as numpy array (H, W, 3), uint8

        Returns:
            List of detections, each with keys:
              - label: str (class name)
              - confidence: float [0, 1]
              - bbox: [x, y, w, h] normalized to [0, 1]
              - bbox_pixels: [x, y, w, h] in pixel coordinates
              - class_id: int
        """
        if self._model is None:
            self.load_model()

        start = time.perf_counter()

        if self._model == "mock":
            detections = self._mock_detect(frame)
        elif self.backend == "ultralytics":
            detections = self._detect_ultralytics(frame)
        elif self.backend == "onnxruntime":
            detections = self._detect_onnx(frame)
        else:
            detections = []

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.debug(
            f"Detection: {len(detections)} objects in {elapsed_ms:.1f}ms"
        )
        return detections

    def _detect_ultralytics(self, frame: np.ndarray) -> List[Dict]:
        """YOLO ultralytics backend inference."""
        results = self._model(
            frame,
            conf=self.confidence,
            iou=self.nms_threshold,
            imgsz=self.input_size[0],
            verbose=False,
        )

        detections = []
        h, w = frame.shape[:2]

        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for i in range(len(boxes)):
                xyxy = boxes.xyxy[i].cpu().numpy()
                conf = float(boxes.conf[i])
                cls_id = int(boxes.cls[i])
                label = result.names.get(cls_id, f"class_{cls_id}")

                x1, y1, x2, y2 = xyxy
                detections.append({
                    "label": label,
                    "confidence": round(conf, 3),
                    "bbox": [
                        round(float(x1 / w), 4),
                        round(float(y1 / h), 4),
                        round(float((x2 - x1) / w), 4),
                        round(float((y2 - y1) / h), 4),
                    ],
                    "bbox_pixels": [
                        int(x1), int(y1), int(x2 - x1), int(y2 - y1)
                    ],
                    "class_id": cls_id,
                })

        return detections

    def _detect_onnx(self, frame: np.ndarray) -> List[Dict]:
        """ONNX Runtime backend inference."""
        h, w = frame.shape[:2]
        import cv2

        # Preprocess
        blob = cv2.resize(frame, self.input_size)
        blob = blob.astype(np.float32) / 255.0
        blob = blob.transpose(2, 0, 1)[np.newaxis, ...]  # NCHW

        input_name = self._model.get_inputs()[0].name
        outputs = self._model.run(None, {input_name: blob})

        # Parse YOLO output format: [batch, num_detections, 5 + num_classes]
        predictions = outputs[0][0]

        detections = []
        for pred in predictions:
            conf = pred[4]
            if conf < self.confidence:
                continue
            class_scores = pred[5:]
            cls_id = int(np.argmax(class_scores))
            score = conf * class_scores[cls_id]
            if score < self.confidence:
                continue

            cx, cy, bw, bh = pred[:4]
            x = (cx - bw / 2) / self.input_size[0]
            y = (cy - bh / 2) / self.input_size[1]
            nw = bw / self.input_size[0]
            nh = bh / self.input_size[1]

            label = (
                self.GROCERY_CLASSES[cls_id]
                if cls_id < len(self.GROCERY_CLASSES)
                else f"class_{cls_id}"
            )
            detections.append({
                "label": label,
                "confidence": round(float(score), 3),
                "bbox": [round(float(v), 4) for v in [x, y, nw, nh]],
                "bbox_pixels": [
                    int(x * w), int(y * h), int(nw * w), int(nh * h)
                ],
                "class_id": cls_id,
            })

        return detections

    def _mock_detect(self, frame: np.ndarray) -> List[Dict]:
        """
        Generate realistic mock detections for pipeline testing.
        Produces 0-3 random detections per frame.
        """
        h, w = frame.shape[:2]
        num_detections = np.random.randint(0, 4)
        detections = []

        for _ in range(num_detections):
            cls_id = np.random.randint(0, len(self.GROCERY_CLASSES))
            cx = np.random.uniform(0.2, 0.8)
            cy = np.random.uniform(0.2, 0.8)
            bw = np.random.uniform(0.05, 0.2)
            bh = np.random.uniform(0.05, 0.2)
            conf = np.random.uniform(0.55, 0.98)

            detections.append({
                "label": self.GROCERY_CLASSES[cls_id],
                "confidence": round(float(conf), 3),
                "bbox": [
                    round(cx - bw / 2, 4),
                    round(cy - bh / 2, 4),
                    round(bw, 4),
                    round(bh, 4),
                ],
                "bbox_pixels": [
                    int((cx - bw / 2) * w),
                    int((cy - bh / 2) * h),
                    int(bw * w),
                    int(bh * h),
                ],
                "class_id": cls_id,
            })

        return detections
