"""
Test Evaluation Tracker

Verifies metric computation and delta tracking.
"""

import pytest
import tempfile
from pathlib import Path
from datashark_mcp.agentic.learning.evaluation_tracker import EvaluationTracker


@pytest.fixture
def sample_instance():
    """Create sample instance."""
    with tempfile.TemporaryDirectory() as tmpdir:
        instance_path = Path(tmpdir) / "test_instance"
        instance_path.mkdir()
        yield instance_path


def test_evaluation_tracker_precision_recall(sample_instance):
    """Test precision and recall computation."""
    tracker = EvaluationTracker(sample_instance)
    
    relevant = ["a", "b", "c"]
    retrieved = ["a", "b", "d"]
    
    precision = tracker.compute_precision(retrieved, relevant)
    recall = tracker.compute_recall(relevant, retrieved)
    
    assert 0.0 <= precision <= 1.0
    assert 0.0 <= recall <= 1.0
    assert precision == 2/3  # 2 relevant out of 3 retrieved
    assert recall == 2/3  # 2 retrieved out of 3 relevant


def test_evaluation_tracker_latency_delta(sample_instance):
    """Test latency delta computation."""
    tracker = EvaluationTracker(sample_instance)
    
    baseline = 100.0
    current = 120.0
    
    delta = tracker.compute_latency_delta(current, baseline)
    
    assert delta == 20.0


def test_evaluation_tracker_summary_with_deltas(sample_instance):
    """Test metrics summary with delta tracking."""
    tracker = EvaluationTracker(sample_instance)
    
    # Record some metrics
    tracker.record_metric("accuracy", 0.85)
    tracker.record_metric("precision", 0.80)
    tracker.record_metric("recall", 0.90)
    tracker.record_metric("latency", 200.0)
    
    # Get summary
    summary1 = tracker.get_metrics_summary()
    
    # Record updated metrics
    tracker.record_metric("accuracy", 0.90)
    tracker.record_metric("latency", 180.0)
    
    # Get summary again
    summary2 = tracker.get_metrics_summary()
    
    # Should have deltas
    assert "accuracy_delta" in summary2 or "latency_delta_ms" in summary2


def test_evaluation_tracker_deterministic(sample_instance):
    """Test that metric computation is deterministic."""
    tracker = EvaluationTracker(sample_instance)
    
    # Same inputs should produce same outputs
    precision1 = tracker.compute_precision(["a", "b"], ["a", "b", "c"])
    precision2 = tracker.compute_precision(["a", "b"], ["a", "b", "c"])
    
    assert precision1 == precision2

