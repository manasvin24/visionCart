"""
VisionCart – Freshness Detection Engine

Heuristic-based produce quality assessment using color and texture analysis.
Designed for edge deployment with sub-5ms inference on CPU.

Methodology:
  1. Extract the Region of Interest (ROI) from the detected bounding box
  2. Convert to multiple color spaces (HSV, LAB) for robust analysis
  3. Score based on:
     a. Color distribution – deviation from "ideal" color profile per produce type
     b. Brown/dark spot detection – bruising indicator
     c. Texture uniformity – via Laplacian variance (blur = overripe)
     d. Surface consistency – edge density analysis
  4. Weighted combination produces a [0, 1] freshness score

Score interpretation:
  0.85 - 1.00 → Excellent (bright, firm, no blemishes)
  0.65 - 0.84 → Good (minor imperfections, still fresh)
  0.40 - 0.64 → Fair (visible aging, some brown spots)
  0.00 - 0.39 → Poor (significant bruising, overripe)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("visioncart.freshness")


# ── Ideal Color Profiles (HSV) per Produce Type ──────────────────────────────

# Each profile: (hue_center, hue_range, sat_min, val_min)
# Hue is in [0, 180] (OpenCV convention)
PRODUCE_COLOR_PROFILES: Dict[str, Dict[str, Any]] = {
    "banana": {
        "ideal_hue": (25, 35),      # Yellow
        "overripe_hue": (15, 25),    # Brown-yellow
        "unripe_hue": (35, 75),      # Green
        "min_saturation": 80,
        "min_value": 100,
        "bruise_hue": (5, 20),       # Dark brown
    },
    "apple": {
        "ideal_hue": (0, 15),        # Red
        "overripe_hue": (10, 25),    # Brown-red
        "min_saturation": 60,
        "min_value": 80,
        "bruise_hue": (10, 30),
        "green_variant_hue": (35, 85),
    },
    "orange": {
        "ideal_hue": (10, 25),
        "overripe_hue": (5, 15),
        "min_saturation": 100,
        "min_value": 120,
        "bruise_hue": (0, 10),
    },
    "tomato": {
        "ideal_hue": (0, 10),
        "overripe_hue": (170, 180),
        "min_saturation": 80,
        "min_value": 80,
        "bruise_hue": (0, 5),
    },
    "avocado": {
        "ideal_hue": (35, 80),       # Dark green
        "overripe_hue": (10, 35),    # Brown
        "min_saturation": 30,
        "min_value": 30,
        "bruise_hue": (0, 15),
    },
    "grape": {
        "ideal_hue": (120, 160),     # Purple
        "overripe_hue": (100, 125),
        "min_saturation": 40,
        "min_value": 40,
        "bruise_hue": (0, 10),
    },
    "strawberry": {
        "ideal_hue": (0, 10),
        "overripe_hue": (160, 180),
        "min_saturation": 100,
        "min_value": 60,
        "bruise_hue": (0, 5),
    },
    "lettuce": {
        "ideal_hue": (35, 85),
        "overripe_hue": (20, 40),    # Yellowing
        "min_saturation": 40,
        "min_value": 60,
        "bruise_hue": (10, 25),      # Brown edges
    },
    "broccoli": {
        "ideal_hue": (35, 80),
        "overripe_hue": (20, 40),
        "min_saturation": 40,
        "min_value": 50,
        "bruise_hue": (15, 30),
    },
}

# Default profile for unknown produce
DEFAULT_PROFILE = {
    "ideal_hue": (20, 80),
    "overripe_hue": (10, 25),
    "min_saturation": 50,
    "min_value": 50,
    "bruise_hue": (0, 20),
}


class FreshnessDetector:
    """
    Analyzes produce freshness from a cropped image region.
    All operations use vectorized NumPy for edge-speed performance.
    """

    def __init__(self, bruise_threshold: float = 0.65):
        self.bruise_threshold = bruise_threshold

    def analyze(
        self,
        roi: np.ndarray,
        produce_type: str = "unknown",
    ) -> Dict[str, Any]:
        """
        Compute a freshness score for a produce region of interest.

        Args:
            roi: BGR image crop of the detected produce (H, W, 3), uint8
            produce_type: Label from object detection (e.g., "banana", "apple")

        Returns:
            Dict with:
              - score: float [0, 1] overall freshness
              - grade: str ("excellent" | "good" | "fair" | "poor")
              - details: Dict of sub-scores
              - is_bruised: bool
              - recommendation: str
        """
        if roi.size == 0 or roi.shape[0] < 5 or roi.shape[1] < 5:
            return self._empty_result("ROI too small for analysis")

        # Convert to color spaces
        import cv2
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB)
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        profile = PRODUCE_COLOR_PROFILES.get(produce_type, DEFAULT_PROFILE)

        # ── Sub-score computations ──
        color_score = self._color_score(hsv, profile)
        bruise_score = self._bruise_score(hsv, profile)
        texture_score = self._texture_score(gray)
        uniformity_score = self._uniformity_score(lab)

        # ── Weighted combination ──
        weights = {
            "color": 0.30,
            "bruise": 0.35,
            "texture": 0.20,
            "uniformity": 0.15,
        }
        overall = (
            color_score * weights["color"]
            + bruise_score * weights["bruise"]
            + texture_score * weights["texture"]
            + uniformity_score * weights["uniformity"]
        )
        overall = float(np.clip(overall, 0.0, 1.0))

        # ── Grade and recommendation ──
        grade, recommendation = self._grade(overall, produce_type)
        is_bruised = bruise_score < self.bruise_threshold

        return {
            "score": round(overall, 3),
            "grade": grade,
            "is_bruised": is_bruised,
            "details": {
                "color_score": round(color_score, 3),
                "bruise_score": round(bruise_score, 3),
                "texture_score": round(texture_score, 3),
                "uniformity_score": round(uniformity_score, 3),
            },
            "weights": weights,
            "produce_type": produce_type,
            "recommendation": recommendation,
        }

    def _color_score(self, hsv: np.ndarray, profile: Dict) -> float:
        """
        Score based on how well the hue distribution matches the ideal.
        Higher score = closer to ideal fresh color.
        """
        hue = hsv[:, :, 0].astype(np.float32)
        sat = hsv[:, :, 1].astype(np.float32)

        ideal_low, ideal_high = profile["ideal_hue"]
        min_sat = profile.get("min_saturation", 50)

        # Mask out low-saturation pixels (background/specular highlights)
        valid_mask = sat > min_sat
        if valid_mask.sum() < 10:
            return 0.5  # Insufficient data

        valid_hue = hue[valid_mask]

        # Percentage of pixels within ideal hue range
        in_ideal = np.logical_and(valid_hue >= ideal_low, valid_hue <= ideal_high)
        ideal_ratio = in_ideal.sum() / len(valid_hue)

        # Penalize pixels in overripe range
        overripe_low, overripe_high = profile.get("overripe_hue", (0, 0))
        in_overripe = np.logical_and(
            valid_hue >= overripe_low, valid_hue <= overripe_high
        )
        overripe_ratio = in_overripe.sum() / len(valid_hue)

        score = ideal_ratio * 0.8 + (1 - overripe_ratio) * 0.2
        return float(np.clip(score, 0, 1))

    def _bruise_score(self, hsv: np.ndarray, profile: Dict) -> float:
        """
        Detect brown/dark patches (bruising).
        Higher score = fewer bruises = fresher.
        """
        hue = hsv[:, :, 0].astype(np.float32)
        sat = hsv[:, :, 1].astype(np.float32)
        val = hsv[:, :, 2].astype(np.float32)

        bruise_low, bruise_high = profile.get("bruise_hue", (0, 20))
        min_val = profile.get("min_value", 50)

        # Bruise pixels: brown hue + low value + moderate saturation
        bruise_mask = (
            (hue >= bruise_low)
            & (hue <= bruise_high)
            & (val < min_val * 1.2)
            & (sat > 20)
        )

        total_pixels = hue.shape[0] * hue.shape[1]
        bruise_ratio = bruise_mask.sum() / max(total_pixels, 1)

        # Also check for very dark spots (any hue, very low value)
        dark_mask = val < 40
        dark_ratio = dark_mask.sum() / max(total_pixels, 1)

        # Combine: more bruises/dark spots → lower score
        combined_ratio = bruise_ratio * 0.7 + dark_ratio * 0.3
        score = 1.0 - min(combined_ratio * 5.0, 1.0)  # Scale up: 20% bruised → score 0
        return float(np.clip(score, 0, 1))

    def _texture_score(self, gray: np.ndarray) -> float:
        """
        Texture analysis via Laplacian variance.
        Sharp, well-defined texture = fresh. Mushy/blurry = overripe.
        """
        import cv2

        # Laplacian measures edge sharpness
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        variance = laplacian.var()

        # Normalize: typical fresh produce has variance 200-2000
        # Overripe/mushy: < 100. Very textured/rough: > 2000.
        if variance < 50:
            score = 0.2
        elif variance < 200:
            score = 0.2 + (variance - 50) / 150 * 0.4
        elif variance < 1500:
            score = 0.6 + (variance - 200) / 1300 * 0.4
        else:
            score = 1.0 - min((variance - 1500) / 3000, 0.3)  # Too rough can be bad

        return float(np.clip(score, 0, 1))

    def _uniformity_score(self, lab: np.ndarray) -> float:
        """
        Surface uniformity via LAB color space standard deviation.
        Uniform color = fresh. Splotchy/varied = aging.
        """
        # Use the a* and b* channels (color information)
        a_channel = lab[:, :, 1].astype(np.float32)
        b_channel = lab[:, :, 2].astype(np.float32)

        a_std = np.std(a_channel)
        b_std = np.std(b_channel)
        combined_std = (a_std + b_std) / 2

        # Lower std = more uniform = higher score
        # Typical: fresh produce std 5-15, aging 15-40, very splotchy 40+
        if combined_std < 8:
            score = 1.0
        elif combined_std < 20:
            score = 1.0 - (combined_std - 8) / 12 * 0.4
        elif combined_std < 40:
            score = 0.6 - (combined_std - 20) / 20 * 0.4
        else:
            score = 0.2

        return float(np.clip(score, 0, 1))

    @staticmethod
    def _grade(score: float, produce_type: str) -> Tuple[str, str]:
        """Map numerical score to grade and recommendation."""
        if score >= 0.85:
            return "excellent", f"This {produce_type} looks great! Fresh and vibrant."
        elif score >= 0.65:
            return "good", f"This {produce_type} is in good condition. Minor imperfections only."
        elif score >= 0.40:
            return (
                "fair",
                f"This {produce_type} shows signs of aging. Consider a fresher option.",
            )
        else:
            return (
                "poor",
                f"⚠️ This {produce_type} has significant quality issues. "
                "Recommend choosing a different one.",
            )

    @staticmethod
    def _empty_result(reason: str) -> Dict[str, Any]:
        return {
            "score": 0.0,
            "grade": "unknown",
            "is_bruised": False,
            "details": {},
            "produce_type": "unknown",
            "recommendation": reason,
        }
