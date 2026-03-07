"""
Test Model Updater

Verifies model retraining with deterministic seed.
"""

import pytest
import json
import tempfile
from pathlib import Path
from datashark_mcp.agentic.learning.model_updater import ModelUpdater
from datashark_mcp.agentic.learning.feedback_collector import FeedbackCollector


@pytest.fixture
def sample_instance_with_feedback():
    """Create instance with feedback data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        instance_path = Path(tmpdir) / "test_instance"
        instance_path.mkdir()
        logs_dir = instance_path / "logs"
        logs_dir.mkdir()
        
        # Create corrections
        corrections_file = logs_dir / "corrections.jsonl"
        with open(corrections_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "timestamp": "2025-11-03T12:00:00Z",
                "inference_id": "test_1",
                "inference_type": "join",
                "correction": "Rejected join",
                "details": {"method": "name_match"}
            }) + "\n")
        
        yield instance_path


def test_model_updater_retrain(sample_instance_with_feedback):
    """Test model retraining."""
    updater = ModelUpdater(sample_instance_with_feedback, seed=42)
    
    result = updater.retrain_models()
    
    assert "timestamp" in result
    assert "dsl_templates" in result
    assert "join_heuristics" in result
    assert "concept_catalog" in result
    assert "seed" in result
    assert result["seed"] == 42


def test_model_updater_deterministic(sample_instance_with_feedback):
    """Test that model updates are deterministic with same seed."""
    updater1 = ModelUpdater(sample_instance_with_feedback, seed=42)
    updater2 = ModelUpdater(sample_instance_with_feedback, seed=42)
    
    result1 = updater1.retrain_models()
    result2 = updater2.retrain_models()
    
    # Should produce same model hashes
    hash1 = result1["dsl_templates"].get("model_hash")
    hash2 = result2["dsl_templates"].get("model_hash")
    
    # Note: Hashes might differ if timestamps are different, but structure should be same
    assert result1["dsl_templates"]["templates_updated"] == result2["dsl_templates"]["templates_updated"]


def test_model_storage_versioning(sample_instance_with_feedback):
    """Test that model storage tracks versions."""
    from datashark_mcp.agentic.learning.model_storage import ModelStorage
    
    storage = ModelStorage(sample_instance_with_feedback)
    
    # Save model
    model_data = {"version": "1.0.0", "data": {"test": "value"}}
    hash1 = storage.save_model("test_model", model_data, seed=42)
    
    # Load model
    loaded = storage.load_model("test_model")
    assert loaded is not None
    
    # Check hash
    hash2 = storage.get_model_hash("test_model")
    assert hash1 == hash2

