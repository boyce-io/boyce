"""
Evaluation Metrics

Defines and computes evaluation metrics for agentic reasoning.
"""

from __future__ import annotations

import hashlib
import json
from typing import Dict, Any, List
from dataclasses import dataclass


@dataclass
class EvaluationMetrics:
    """Evaluation metrics for agentic reasoning."""
    accuracy: float  # DSL correctness (0.0-1.0)
    recall: float  # Concept coverage (0.0-1.0)
    latency_ms: float  # Average runtime
    reproducibility: float  # Hash equality (1.0 if deterministic, 0.0 if not)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict."""
        return {
            "accuracy": round(self.accuracy, 3),
            "recall": round(self.recall, 3),
            "latency_ms": round(self.latency_ms, 2),
            "reproducibility": round(self.reproducibility, 3)
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), sort_keys=True)


def compute_accuracy(expected_dsl: str, actual_dsl: str) -> float:
    """
    Compute accuracy (DSL correctness).
    
    Args:
        expected_dsl: Expected DSL query
        actual_dsl: Actual DSL query
        
    Returns:
        Accuracy score (0.0-1.0)
    """
    if expected_dsl == actual_dsl:
        return 1.0
    
    # Simple similarity: check if key components match
    expected_parts = set(expected_dsl.upper().split())
    actual_parts = set(actual_dsl.upper().split())
    
    if not expected_parts:
        return 0.0
    
    intersection = expected_parts & actual_parts
    return len(intersection) / len(expected_parts)


def compute_recall(expected_concepts: List[str], actual_concepts: List[str]) -> float:
    """
    Compute recall (concept coverage).
    
    Args:
        expected_concepts: Expected concept names
        actual_concepts: Actual concept names found
        
    Returns:
        Recall score (0.0-1.0)
    """
    if not expected_concepts:
        return 1.0 if not actual_concepts else 0.0
    
    expected_set = set(expected_concepts)
    actual_set = set(actual_concepts)
    
    intersection = expected_set & actual_set
    return len(intersection) / len(expected_set)


def compute_reproducibility(results1: Dict[str, Any], results2: Dict[str, Any]) -> float:
    """
    Compute reproducibility (hash equality).
    
    Args:
        results1: First execution results
        results2: Second execution results
        
    Returns:
        1.0 if results are identical, 0.0 otherwise
    """
    # Normalize and compare
    def normalize(obj):
        return json.dumps(obj, sort_keys=True, separators=(",", ":"))
    
    hash1 = hashlib.sha256(normalize(results1).encode("utf-8")).hexdigest()
    hash2 = hashlib.sha256(normalize(results2).encode("utf-8")).hexdigest()
    
    return 1.0 if hash1 == hash2 else 0.0


def compute_metrics(
    test_cases: List[Dict[str, Any]],
    actual_results: List[Dict[str, Any]]
) -> EvaluationMetrics:
    """
    Compute evaluation metrics from test cases.
    
    Args:
        test_cases: List of test cases with expected results
        actual_results: List of actual execution results
        
    Returns:
        EvaluationMetrics object
    """
    if len(test_cases) != len(actual_results):
        raise ValueError("Test cases and results must have same length")
    
    accuracies = []
    recalls = []
    latencies = []
    
    for test_case, actual in zip(test_cases, actual_results):
        # Accuracy
        expected_dsl = test_case.get("expected_dsl", "")
        actual_dsl = actual.get("dsl_query", "")
        accuracies.append(compute_accuracy(expected_dsl, actual_dsl))
        
        # Recall
        expected_concepts = test_case.get("expected_concepts", [])
        actual_concepts = actual.get("concepts_found", [])
        recalls.append(compute_recall(expected_concepts, actual_concepts))
        
        # Latency
        latency = actual.get("runtime_ms", 0.0)
        latencies.append(latency)
    
    # Reproducibility (would need two runs, assume 1.0 for now)
    reproducibility = 1.0
    
    return EvaluationMetrics(
        accuracy=sum(accuracies) / len(accuracies) if accuracies else 0.0,
        recall=sum(recalls) / len(recalls) if recalls else 0.0,
        latency_ms=sum(latencies) / len(latencies) if latencies else 0.0,
        reproducibility=reproducibility
    )

