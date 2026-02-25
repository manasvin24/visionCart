"""
VisionCart – Order Reconciliation Engine

Compares items detected by the AI vision pipeline against the digital
shopping list to track fulfillment progress in real-time.

Features:
  - Fuzzy label matching (handles YOLO class variations)
  - Quantity tracking (multiple units of the same item)
  - Confidence-weighted matching (high confidence → auto-match,
    low confidence → suggest to user)
  - Substitution detection (detected item not on list but similar category)
"""

from __future__ import annotations

import logging
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("visioncart.reconciliation")


# ── Label Synonym Map ─────────────────────────────────────────────────────────
# Maps YOLO detection labels to canonical inventory names

LABEL_SYNONYMS: Dict[str, List[str]] = {
    "banana": ["banana", "cavendish_banana", "plantain"],
    "apple": ["apple", "red_apple", "green_apple", "fuji_apple", "gala_apple"],
    "orange": ["orange", "navel_orange", "mandarin", "tangerine", "clementine"],
    "tomato": ["tomato", "cherry_tomato", "roma_tomato", "beefsteak_tomato"],
    "potato": ["potato", "russet_potato", "red_potato", "sweet_potato"],
    "onion": ["onion", "red_onion", "white_onion", "yellow_onion"],
    "grape": ["grape", "red_grape", "green_grape", "grape_bunch"],
    "lettuce": ["lettuce", "romaine", "iceberg", "butter_lettuce"],
    "pepper": ["pepper", "bell_pepper", "red_pepper", "green_pepper"],
    "chicken": ["chicken", "chicken_breast", "chicken_thigh", "whole_chicken"],
    "bread": ["bread", "white_bread", "wheat_bread", "sourdough", "baguette"],
    "milk": ["milk", "whole_milk", "skim_milk", "2%_milk", "oat_milk"],
    "cheese": ["cheese", "cheddar", "mozzarella", "swiss", "parmesan"],
    "yogurt": ["yogurt", "greek_yogurt", "vanilla_yogurt"],
    "egg_carton": ["egg_carton", "eggs", "dozen_eggs"],
}

# Reverse lookup: any synonym → canonical name
_SYNONYM_TO_CANONICAL: Dict[str, str] = {}
for canonical, synonyms in LABEL_SYNONYMS.items():
    for synonym in synonyms:
        _SYNONYM_TO_CANONICAL[synonym.lower()] = canonical


class OrderReconciler:
    """
    Matches AI detections against the shopping list in real-time.
    """

    def __init__(
        self,
        auto_match_threshold: float = 0.80,
        suggest_threshold: float = 0.55,
        fuzzy_match_threshold: float = 0.70,
    ):
        """
        Args:
            auto_match_threshold: Detection confidence above which items are
                auto-matched without user confirmation.
            suggest_threshold: Minimum confidence for suggesting a match.
            fuzzy_match_threshold: Minimum string similarity for fuzzy matching
                labels to inventory names.
        """
        self.auto_match_threshold = auto_match_threshold
        self.suggest_threshold = suggest_threshold
        self.fuzzy_match_threshold = fuzzy_match_threshold

    def reconcile(
        self,
        detections: List[Dict[str, Any]],
        shopping_list: List[Dict[str, Any]],
        already_picked: Set[str] = None,
    ) -> Dict[str, Any]:
        """
        Match detected items against the shopping list.

        Args:
            detections: List of AI detections with 'label' and 'confidence' keys.
            shopping_list: List of items with 'item_id', 'name', 'detection_labels',
                           and 'quantity_requested' keys.
            already_picked: Set of item_ids already marked as picked.

        Returns:
            Dict with:
              - matches: confirmed matches (detection ↔ list item)
              - suggestions: low-confidence or fuzzy matches for user review
              - unmatched_detections: detected but not on the list
              - missing_items: on the list but not yet detected
              - progress: fulfillment statistics
        """
        if already_picked is None:
            already_picked = set()

        # Build lookup structures
        remaining_items = [
            item for item in shopping_list
            if item["item_id"] not in already_picked
        ]

        matches = []
        suggestions = []
        unmatched_detections = []
        matched_item_ids = set()

        for detection in detections:
            label = detection.get("label", "").lower()
            confidence = detection.get("confidence", 0)

            if confidence < self.suggest_threshold:
                continue  # Skip very low confidence detections

            # Try exact + synonym matching
            canonical = _SYNONYM_TO_CANONICAL.get(label, label)
            best_match = None
            best_score = 0.0

            for item in remaining_items:
                if item["item_id"] in matched_item_ids:
                    continue

                item_score = self._match_score(
                    canonical, label, item
                )
                if item_score > best_score:
                    best_score = item_score
                    best_match = item

            if best_match and best_score >= self.fuzzy_match_threshold:
                match_entry = {
                    "detection": detection,
                    "item": best_match,
                    "match_score": round(best_score, 3),
                    "match_type": "auto" if confidence >= self.auto_match_threshold else "suggested",
                }

                if confidence >= self.auto_match_threshold and best_score >= 0.85:
                    matches.append(match_entry)
                    matched_item_ids.add(best_match["item_id"])
                else:
                    suggestions.append(match_entry)
            else:
                unmatched_detections.append({
                    "detection": detection,
                    "possible_category": canonical,
                })

        # Items on list but not detected
        missing_items = [
            item for item in remaining_items
            if item["item_id"] not in matched_item_ids
        ]

        # Progress stats
        total_items = len(shopping_list)
        picked_count = len(already_picked) + len(matches)
        progress = {
            "total_items": total_items,
            "picked": picked_count,
            "pending": total_items - picked_count,
            "completion_percent": round(
                (picked_count / max(total_items, 1)) * 100, 1
            ),
        }

        return {
            "matches": matches,
            "suggestions": suggestions,
            "unmatched_detections": unmatched_detections,
            "missing_items": missing_items,
            "progress": progress,
        }

    def _match_score(
        self,
        canonical_label: str,
        raw_label: str,
        item: Dict[str, Any],
    ) -> float:
        """
        Compute a match score between a detection label and a shopping list item.
        Uses both exact matching and fuzzy string similarity.
        """
        item_name = item.get("name", "").lower()
        detection_labels = [
            l.lower() for l in item.get("detection_labels", [])
        ]

        # Exact match on detection_labels (highest confidence)
        if canonical_label in detection_labels or raw_label in detection_labels:
            return 1.0

        # Exact match on item name
        if canonical_label == item_name or raw_label == item_name:
            return 0.95

        # Substring match
        if canonical_label in item_name or item_name in canonical_label:
            return 0.85

        # Fuzzy string matching
        best_fuzzy = 0.0
        candidates = [item_name] + detection_labels
        for candidate in candidates:
            ratio = SequenceMatcher(None, canonical_label, candidate).ratio()
            best_fuzzy = max(best_fuzzy, ratio)
            ratio2 = SequenceMatcher(None, raw_label, candidate).ratio()
            best_fuzzy = max(best_fuzzy, ratio2)

        return best_fuzzy

    def find_substitutes(
        self,
        item: Dict[str, Any],
        available_items: List[Dict[str, Any]],
        max_suggestions: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Find potential substitutes for a missing/poor-quality item.

        Args:
            item: The original item from the shopping list.
            available_items: List of inventory items currently in stock.
            max_suggestions: Maximum number of substitutes to return.

        Returns:
            List of substitute suggestions with similarity scores.
        """
        item_name = item.get("name", "").lower()
        item_category = item.get("category", "").lower()
        original_price = float(item.get("price", 0))

        scored = []
        for candidate in available_items:
            if candidate.get("id") == item.get("inventory_id"):
                continue  # Skip the original item

            score = 0.0
            cand_name = candidate.get("name", "").lower()
            cand_category = candidate.get("category", "").lower()
            cand_price = float(candidate.get("price", 0))

            # Same category is a strong signal
            if cand_category == item_category:
                score += 0.4

            # Name similarity
            name_sim = SequenceMatcher(None, item_name, cand_name).ratio()
            score += name_sim * 0.4

            # Price proximity (prefer similar price)
            if original_price > 0:
                price_ratio = min(cand_price, original_price) / max(
                    cand_price, original_price, 0.01
                )
                score += price_ratio * 0.2

            if score > 0.3:  # Minimum relevance
                scored.append({
                    "item": candidate,
                    "similarity_score": round(score, 3),
                    "price_difference": round(cand_price - original_price, 2),
                })

        # Sort by score descending
        scored.sort(key=lambda x: x["similarity_score"], reverse=True)
        return scored[:max_suggestions]
