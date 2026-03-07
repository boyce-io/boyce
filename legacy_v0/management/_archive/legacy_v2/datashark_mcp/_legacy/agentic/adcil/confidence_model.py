"""
Confidence Model

Stores and manages confidence scores for ADCIL inferences.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import json
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ConfidenceScore:
    """Represents a confidence score for an inference."""
    inference_id: str
    inference_type: str  # "concept" | "join" | "semantic"
    confidence: float
    method: str
    timestamp: str
    accepted: bool
    feedback: Optional[str] = None


class ConfidenceModel:
    """
    Manages confidence scores for ADCIL inferences.
    
    Tracks:
    - Historical confidence scores
    - Acceptance/rejection rates
    - Method effectiveness
    """
    
    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize confidence model.
        
        Args:
            storage_path: Path to store confidence history (optional)
        """
        self.storage_path = storage_path
        self.scores: Dict[str, ConfidenceScore] = {}
        self.method_stats: Dict[str, Dict[str, float]] = {}
        
        if storage_path and storage_path.exists():
            self.load()
    
    def record_score(
        self,
        inference_id: str,
        inference_type: str,
        confidence: float,
        method: str,
        accepted: bool,
        feedback: Optional[str] = None
    ):
        """Record a confidence score."""
        score = ConfidenceScore(
            inference_id=inference_id,
            inference_type=inference_type,
            confidence=confidence,
            method=method,
            timestamp=datetime.utcnow().isoformat() + "Z",
            accepted=accepted,
            feedback=feedback
        )
        
        self.scores[inference_id] = score
        
        # Update method statistics
        if method not in self.method_stats:
            self.method_stats[method] = {
                "total": 0,
                "accepted": 0,
                "avg_confidence": 0.0
            }
        
        stats = self.method_stats[method]
        stats["total"] += 1
        if accepted:
            stats["accepted"] += 1
        
        # Update average confidence
        total = stats["total"]
        current_avg = stats["avg_confidence"]
        stats["avg_confidence"] = ((current_avg * (total - 1)) + confidence) / total
        
        if self.storage_path:
            self.save()
    
    def get_confidence(self, inference_id: str) -> Optional[float]:
        """Get confidence score for an inference."""
        score = self.scores.get(inference_id)
        return score.confidence if score else None
    
    def get_method_effectiveness(self, method: str) -> Dict[str, float]:
        """Get effectiveness metrics for a method."""
        return self.method_stats.get(method, {
            "total": 0,
            "accepted": 0,
            "avg_confidence": 0.0,
            "acceptance_rate": 0.0
        })
    
    def get_optimal_threshold(self, method: str) -> float:
        """
        Calculate optimal confidence threshold for a method based on history.
        
        Returns:
            Confidence threshold that maximizes acceptance rate
        """
        method_scores = [
            (s.confidence, s.accepted)
            for s in self.scores.values()
            if s.method == method
        ]
        
        if not method_scores:
            return 0.7  # Default threshold
        
        # Find threshold that maximizes acceptance rate
        sorted_scores = sorted(method_scores, key=lambda x: x[0], reverse=True)
        
        best_threshold = 0.7
        best_acceptance_rate = 0.0
        
        for i in range(len(sorted_scores)):
            threshold = sorted_scores[i][0]
            accepted_count = sum(1 for _, accepted in sorted_scores[:i+1] if accepted)
            acceptance_rate = accepted_count / (i + 1) if i > 0 else 0
            
            if acceptance_rate > best_acceptance_rate:
                best_acceptance_rate = acceptance_rate
                best_threshold = threshold
        
        return max(0.5, min(0.95, best_threshold))  # Clamp between 0.5 and 0.95
    
    def save(self):
        """Save confidence scores to disk."""
        if not self.storage_path:
            return
        
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "scores": {
                k: asdict(v) for k, v in self.scores.items()
            },
            "method_stats": self.method_stats
        }
        
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    
    def load(self):
        """Load confidence scores from disk."""
        if not self.storage_path or not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self.scores = {
                k: ConfidenceScore(**v)
                for k, v in data.get("scores", {}).items()
            }
            self.method_stats = data.get("method_stats", {})
            
            logger.info(f"Loaded {len(self.scores)} confidence scores")
        except Exception as e:
            logger.warning(f"Failed to load confidence scores: {e}")

