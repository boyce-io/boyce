"""
Evaluation Tracker

Stores accuracy/recall/latency metrics over time.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class EvaluationTracker:
    """
    Tracks evaluation metrics:
    - Accuracy (DSL correctness)
    - Recall (concept coverage)
    - Latency (runtime_ms)
    - Reproducibility (hash equality)
    """
    
    def __init__(self, instance_path: Path):
        """
        Initialize evaluation tracker.
        
        Args:
            instance_path: Path to instance directory
        """
        self.instance_path = instance_path
        self.logs_dir = instance_path / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initialized EvaluationTracker for instance: {instance_path}")
    
    def record_metric(
        self,
        metric_name: str,
        value: float,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Record an evaluation metric.
        
        Args:
            metric_name: Name of metric (e.g., "accuracy", "recall", "latency")
            value: Metric value
            context: Additional context
        """
        metrics_file = self.logs_dir / "learning_metrics.jsonl"
        
        from datashark_mcp.context.determinism import normalize_timestamp
        
        # Normalize timestamp and round values for determinism
        metric_entry = {
            "timestamp": normalize_timestamp(datetime.utcnow().isoformat() + "Z", content=f"{metric_name}:{value}"),
            "metric": metric_name,
            "value": round(value, 2) if isinstance(value, float) else value,  # Round to 2 decimals
            "context": dict(sorted((context or {}).items()))  # Sort keys for determinism
        }
        
        with open(metrics_file, "a", encoding="utf-8") as f:
            # Sort keys for deterministic JSON output
            f.write(json.dumps(metric_entry, sort_keys=True) + "\n")
        
        logger.debug(f"Recorded metric: {metric_name} = {value}")
    
    def compute_accuracy(self, expected: List[Any], actual: List[Any]) -> float:
        """
        Compute accuracy metric.
        
        Args:
            expected: Expected results
            actual: Actual results
            
        Returns:
            Accuracy score (0.0 to 1.0)
        """
        if not expected:
            return 0.0
        
        matches = sum(1 for e, a in zip(expected, actual) if e == a)
        accuracy = matches / len(expected)
        
        self.record_metric("accuracy", accuracy, {
            "expected_count": len(expected),
            "actual_count": len(actual),
            "matches": matches
        })
        
        return accuracy
    
    def compute_recall(self, relevant: List[Any], retrieved: List[Any]) -> float:
        """
        Compute recall metric.
        
        Args:
            relevant: Relevant items
            retrieved: Retrieved items
            
        Returns:
            Recall score (0.0 to 1.0)
        """
        if not relevant:
            return 0.0
        
        relevant_retrieved = set(retrieved) & set(relevant)
        recall = len(relevant_retrieved) / len(relevant) if relevant else 0.0
        
        self.record_metric("recall", recall, {
            "relevant_count": len(relevant),
            "retrieved_count": len(retrieved),
            "relevant_retrieved": len(relevant_retrieved)
        })
        
        return recall
    
    def record_latency(self, operation: str, latency_ms: float):
        """
        Record latency metric.
        
        Args:
            operation: Operation name
            latency_ms: Latency in milliseconds
        """
        self.record_metric("latency", latency_ms, {
            "operation": operation
        })
    
    def compute_precision(self, retrieved: List[Any], relevant: List[Any]) -> float:
        """
        Compute precision metric.
        
        Args:
            retrieved: Retrieved items
            relevant: Relevant items
            
        Returns:
            Precision score (0.0 to 1.0)
        """
        if not retrieved:
            return 0.0
        
        relevant_retrieved = set(retrieved) & set(relevant)
        precision = len(relevant_retrieved) / len(retrieved) if retrieved else 0.0
        
        self.record_metric("precision", precision, {
            "retrieved_count": len(retrieved),
            "relevant_count": len(relevant),
            "relevant_retrieved": len(relevant_retrieved)
        })
        
        return precision
    
    def compute_latency_delta(self, current_latency_ms: float, baseline_latency_ms: float) -> float:
        """
        Compute latency delta vs baseline.
        
        Args:
            current_latency_ms: Current latency
            baseline_latency_ms: Baseline latency
            
        Returns:
            Delta in milliseconds
        """
        delta = current_latency_ms - baseline_latency_ms
        
        self.record_metric("latency_delta", delta, {
            "current_ms": current_latency_ms,
            "baseline_ms": baseline_latency_ms,
            "delta_ms": delta,
            "percent_change": (delta / baseline_latency_ms * 100) if baseline_latency_ms > 0 else 0.0
        })
        
        return delta
    
    def get_metrics_summary(self, since: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Get summary of metrics since given timestamp.
        
        Args:
            since: Optional timestamp to filter metrics
            
        Returns:
            Summary dict with aggregated metrics and deltas
        """
        metrics_file = self.logs_dir / "learning_metrics.jsonl"
        history_file = self.logs_dir / "learning_history.jsonl"
        
        if not metrics_file.exists():
            return {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "total_metrics": 0,
                "avg_accuracy": 0.0,
                "avg_precision": 0.0,
                "avg_recall": 0.0,
                "avg_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
                "latency_delta_ms": 0.0
            }
        
        metrics = []
        with open(metrics_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    metric = json.loads(line)
                    metric_time = datetime.fromisoformat(metric["timestamp"].replace("Z", "+00:00"))
                    if since is None or metric_time >= since:
                        metrics.append(metric)
        
        # Aggregate
        accuracy_values = [m["value"] for m in metrics if m["metric"] == "accuracy"]
        precision_values = [m["value"] for m in metrics if m["metric"] == "precision"]
        recall_values = [m["value"] for m in metrics if m["metric"] == "recall"]
        latency_values = [m["value"] for m in metrics if m["metric"] == "latency"]
        latency_deltas = [m["value"] for m in metrics if m["metric"] == "latency_delta"]
        
        # Get previous run for delta calculation
        previous_summary = None
        if history_file.exists():
            with open(history_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                if lines:
                    try:
                        previous_summary = json.loads(lines[-1])
                    except:
                        pass
        
        from datashark_mcp.context.determinism import normalize_timestamp
        
        # Normalize timestamp and round all numeric values for determinism
        content_key = f"{len(metrics)}:{len(accuracy_values)}:{len(latency_values)}"
        normalized_ts = normalize_timestamp(datetime.utcnow().isoformat() + "Z", content=content_key)
        
        summary = {
            "timestamp": normalized_ts,
            "total_metrics": len(metrics),
            "avg_accuracy": round(sum(accuracy_values) / len(accuracy_values) if accuracy_values else 0.0, 2),
            "avg_precision": round(sum(precision_values) / len(precision_values) if precision_values else 0.0, 2),
            "avg_recall": round(sum(recall_values) / len(recall_values) if recall_values else 0.0, 2),
            "avg_latency_ms": round(sum(latency_values) / len(latency_values) if latency_values else 0.0, 2),
            "p95_latency_ms": round(sorted(latency_values)[int(len(latency_values) * 0.95)] if latency_values else 0.0, 2),
            "latency_delta_ms": round(sum(latency_deltas) / len(latency_deltas) if latency_deltas else 0.0, 2)
        }
        
        # Calculate deltas vs previous run
        if previous_summary:
            summary["accuracy_delta"] = round(summary["avg_accuracy"] - previous_summary.get("avg_accuracy", 0.0), 2)
            summary["recall_delta"] = round(summary["avg_recall"] - previous_summary.get("avg_recall", 0.0), 2)
            summary["precision_delta"] = round(summary["avg_precision"] - previous_summary.get("avg_precision", 0.0), 2)
        
        # Append to history with sorted keys for determinism
        with open(history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(summary, sort_keys=True) + "\n")
        
        return summary

