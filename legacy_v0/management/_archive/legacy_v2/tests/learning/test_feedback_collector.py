"""
Test Feedback Collector

Verifies feedback gathering and normalization.
"""

import pytest
import json
import tempfile
from pathlib import Path
from datashark_mcp.agentic.learning.feedback_collector import FeedbackCollector


@pytest.fixture
def sample_instance():
    """Create a sample instance with logs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        instance_path = Path(tmpdir) / "test_instance"
        instance_path.mkdir()
        logs_dir = instance_path / "logs"
        logs_dir.mkdir()
        
        # Create sample telemetry
        telemetry_file = logs_dir / "extraction_telemetry.jsonl"
        with open(telemetry_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "timestamp": "2025-11-03T12:00:00Z",
                "extractor": "database_catalog",
                "extraction_time_ms": 1234,
                "system": "database"
            }) + "\n")
        
        # Create sample corrections
        corrections_file = logs_dir / "corrections.jsonl"
        with open(corrections_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "timestamp": "2025-11-03T12:01:00Z",
                "inference_id": "test_inference_1",
                "inference_type": "join",
                "correction": "Rejected join inference",
                "details": {"method": "name_match"}
            }) + "\n")
        
        yield instance_path


def test_feedback_collector_gather(sample_instance):
    """Test that feedback collector gathers all sources."""
    collector = FeedbackCollector(sample_instance)
    
    feedback = collector.gather_feedback()
    
    assert len(feedback) > 0
    
    # Check normalization schema
    for entry in feedback:
        assert "source" in entry
        assert "context" in entry
        assert "correction" in entry
        assert "outcome" in entry
        assert "timestamp" in entry
        assert "metadata" in entry


def test_feedback_collector_aggregate(sample_instance):
    """Test feedback aggregation."""
    collector = FeedbackCollector(sample_instance)
    
    summary = collector.aggregate_feedback()
    
    assert "timestamp" in summary
    assert "telemetry_events" in summary
    assert "corrections" in summary
    assert "total_feedback_entries" in summary
    assert "metrics" in summary


def test_feedback_collector_record_correction(sample_instance):
    """Test recording user corrections."""
    collector = FeedbackCollector(sample_instance)
    
    collector.record_correction(
        inference_id="test_123",
        inference_type="concept",
        correction="Updated concept mapping",
        details={"old_concept": "Revenue", "new_concept": "Sales"}
    )
    
    corrections = collector.collect_user_corrections()
    assert len(corrections) >= 1
    assert any(c["inference_id"] == "test_123" for c in corrections)


def test_feedback_collector_deterministic(sample_instance):
    """Test that feedback collection is deterministic."""
    collector1 = FeedbackCollector(sample_instance)
    collector2 = FeedbackCollector(sample_instance)
    
    feedback1 = collector1.gather_feedback()
    feedback2 = collector2.gather_feedback()
    
    # Should produce same number of entries
    assert len(feedback1) == len(feedback2)
    
    # Should have same sources
    sources1 = {e["source"] for e in feedback1}
    sources2 = {e["source"] for e in feedback2}
    assert sources1 == sources2

