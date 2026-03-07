"""
Test ADCIL Pipeline

End-to-end pipeline test with sample extractor output.
Verifies deterministic hash matching.
"""

import pytest
import hashlib
import json
import tempfile
from pathlib import Path
from datashark_mcp.context.models import Node, Edge, Provenance
from datashark_mcp.context.store import GraphStore
from datashark_mcp.agentic.adcil.pipeline import ADCILPipeline
from datetime import datetime


@pytest.fixture
def sample_extractor_output():
    """Create sample extractor output (nodes and edges)."""
    nodes = [
        Node(
            id="entity:database:revenue",
            system="database",
            type="ENTITY",
            name="revenue",
            attributes={"table_name": "revenue"},
            provenance=Provenance(
                system="database",
                source_path="test.db",
                extractor_version="0.2.0",
                extracted_at=datetime.utcnow().isoformat() + "Z"
            ),
            schema="public"
        ),
        Node(
            id="field:database:revenue:amount",
            system="database",
            type="FIELD",
            name="amount",
            attributes={"type": "decimal", "table": "revenue"},
            provenance=Provenance(
                system="database",
                source_path="test.db",
                extractor_version="0.2.0",
                extracted_at=datetime.utcnow().isoformat() + "Z"
            ),
            schema="public"
        ),
        Node(
            id="field:database:revenue:customer_id",
            system="database",
            type="FIELD",
            name="customer_id",
            attributes={"type": "integer", "table": "revenue"},
            provenance=Provenance(
                system="database",
                source_path="test.db",
                extractor_version="0.2.0",
                extracted_at=datetime.utcnow().isoformat() + "Z"
            ),
            schema="public"
        ),
        Node(
            id="entity:database:customers",
            system="database",
            type="ENTITY",
            name="customers",
            attributes={"table_name": "customers"},
            provenance=Provenance(
                system="database",
                source_path="test.db",
                extractor_version="0.2.0",
                extracted_at=datetime.utcnow().isoformat() + "Z"
            ),
            schema="public"
        ),
        Node(
            id="field:database:customers:customer_id",
            system="database",
            type="FIELD",
            name="customer_id",
            attributes={"type": "integer", "table": "customers", "primary_key": True},
            provenance=Provenance(
                system="database",
                source_path="test.db",
                extractor_version="0.2.0",
                extracted_at=datetime.utcnow().isoformat() + "Z"
            ),
            schema="public"
        ),
    ]
    
    edges = []  # No initial edges
    
    return nodes, edges


def compute_manifest_hash(manifest_path: Path) -> str:
    """Compute SHA256 hash of manifest file (excluding timestamps)."""
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    
    # Remove non-deterministic fields for hash
    manifest_copy = manifest.copy()
    manifest_copy.pop("build_timestamp_utc", None)
    if "adcil" in manifest_copy:
        manifest_copy["adcil"].pop("inference_timestamp", None)
    
    manifest_str = json.dumps(manifest_copy, sort_keys=True)
    return hashlib.sha256(manifest_str.encode()).hexdigest()


def test_pipeline_deterministic(sample_extractor_output):
    """Test that pipeline produces deterministic results."""
    nodes, edges = sample_extractor_output
    
    # Run pipeline twice with identical inputs
    with tempfile.TemporaryDirectory() as tmpdir:
        instance_path1 = Path(tmpdir) / "instance1"
        instance_path2 = Path(tmpdir) / "instance2"
        
        for instance_path in [instance_path1, instance_path2]:
            instance_path.mkdir(parents=True)
            (instance_path / "manifests").mkdir()
            (instance_path / "cache").mkdir()
            
            # Create config
            config = {
                "adcil": {
                    "enabled": True,
                    "confidence_threshold": 0.7
                }
            }
            config_path = instance_path / "config.yaml"
            import yaml
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f)
        
        # Initialize stores
        store1 = GraphStore()
        store2 = GraphStore()
        
        for node in nodes:
            store1.add_node(node)
            store2.add_node(node)
        
        for edge in edges:
            store1.add_edge(edge)
            store2.add_edge(edge)
        
        # Run pipeline on both
        pipeline1 = ADCILPipeline(store1, instance_path1, config)
        pipeline2 = ADCILPipeline(store2, instance_path2, config)
        
        summary1 = pipeline1.run()
        summary2 = pipeline2.run()
        
        # Should produce identical summaries (excluding timestamps)
        assert summary1["enabled"] == summary2["enabled"]
        assert summary1["concept_inferences"]["total"] == summary2["concept_inferences"]["total"]
        assert summary1["join_inferences"]["total"] == summary2["join_inferences"]["total"]
        
        # Check manifest hashes (should be identical)
        manifest1 = instance_path1 / "manifests" / "manifest.json"
        manifest2 = instance_path2 / "manifests" / "manifest.json"
        
        if manifest1.exists() and manifest2.exists():
            hash1 = compute_manifest_hash(manifest1)
            hash2 = compute_manifest_hash(manifest2)
            assert hash1 == hash2, "Manifest hashes should be identical for deterministic pipeline"


def test_pipeline_manifest_diff_size(sample_extractor_output):
    """Test that pipeline adds expected nodes/edges to manifest."""
    nodes, edges = sample_extractor_output
    
    with tempfile.TemporaryDirectory() as tmpdir:
        instance_path = Path(tmpdir) / "instance"
        instance_path.mkdir(parents=True)
        (instance_path / "manifests").mkdir()
        (instance_path / "cache").mkdir()
        
        config = {
            "adcil": {
                "enabled": True,
                "confidence_threshold": 0.7
            }
        }
        config_path = instance_path / "config.yaml"
        import yaml
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f)
        
        store = GraphStore()
        for node in nodes:
            store.add_node(node)
        for edge in edges:
            store.add_edge(edge)
        
        # Initial node/edge counts
        initial_nodes = len(store.nodes())
        initial_edges = len(store.edges())
        
        # Run pipeline
        pipeline = ADCILPipeline(store, instance_path, config)
        summary = pipeline.run()
        
        # Final node/edge counts
        final_nodes = len(store.nodes())
        final_edges = len(store.edges())
        
        # Should have added nodes (concepts) and edges (DESCRIBES, RELATES_TO)
        assert final_nodes > initial_nodes, "Should add concept nodes"
        assert final_edges > initial_edges, "Should add concept and join edges"
        
        # Check manifest
        manifest_path = instance_path / "manifests" / "manifest.json"
        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            
            assert "adcil" in manifest
            assert manifest["adcil"]["concept_nodes"] > 0
            assert manifest["adcil"]["concept_edges"] > 0


def test_pipeline_performance(sample_extractor_output):
    """Test that pipeline meets performance targets (p95 < 300ms)."""
    import time
    
    nodes, edges = sample_extractor_output
    
    runtimes = []
    
    for _ in range(10):  # Run 10 times to get p95
        with tempfile.TemporaryDirectory() as tmpdir:
            instance_path = Path(tmpdir) / "instance"
            instance_path.mkdir(parents=True)
            (instance_path / "manifests").mkdir()
            (instance_path / "cache").mkdir()
            
            config = {
                "adcil": {
                    "enabled": True,
                    "confidence_threshold": 0.7
                }
            }
            config_path = instance_path / "config.yaml"
            import yaml
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f)
            
            store = GraphStore()
            for node in nodes:
                store.add_node(node)
            for edge in edges:
                store.add_edge(edge)
            
            pipeline = ADCILPipeline(store, instance_path, config)
            
            start = time.time()
            summary = pipeline.run()
            elapsed_ms = (time.time() - start) * 1000
            
            runtimes.append(elapsed_ms)
    
    # Calculate p95
    runtimes_sorted = sorted(runtimes)
    p95_index = int(len(runtimes_sorted) * 0.95)
    p95_runtime = runtimes_sorted[p95_index]
    
    assert p95_runtime < 300, f"p95 runtime ({p95_runtime:.1f}ms) exceeds 300ms target"


def test_pipeline_disabled(sample_extractor_output):
    """Test that pipeline can be disabled via config."""
    nodes, edges = sample_extractor_output
    
    with tempfile.TemporaryDirectory() as tmpdir:
        instance_path = Path(tmpdir) / "instance"
        instance_path.mkdir(parents=True)
        (instance_path / "manifests").mkdir()
        (instance_path / "cache").mkdir()
        
        config = {
            "adcil": {
                "enabled": False  # Disabled
            }
        }
        config_path = instance_path / "config.yaml"
        import yaml
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f)
        
        store = GraphStore()
        for node in nodes:
            store.add_node(node)
        for edge in edges:
            store.add_edge(edge)
        
        initial_nodes = len(store.nodes())
        initial_edges = len(store.edges())
        
        pipeline = ADCILPipeline(store, instance_path, config)
        summary = pipeline.run()
        
        # Should not have added anything
        assert summary["enabled"] == False
        
        final_nodes = len(store.nodes())
        final_edges = len(store.edges())
        
        assert final_nodes == initial_nodes
        assert final_edges == initial_edges

