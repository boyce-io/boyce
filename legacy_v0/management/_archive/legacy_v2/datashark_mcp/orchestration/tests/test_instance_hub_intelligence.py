"""
Tests for FederatedIntelligenceManager
"""

from pathlib import Path
from datashark_mcp.orchestration.instance_hub import InstanceHub, FederatedIntelligenceManager


def test_compute_confidence_weights_deterministic(tmp_path: Path):
    hub = InstanceHub()
    fim = FederatedIntelligenceManager(hub)

    metrics = {
        "instances": {
            "a": {"avg_accuracy": 0.9, "avg_precision": 0.8, "avg_recall": 0.7, "avg_latency_ms": 100.0},
            "b": {"avg_accuracy": 0.7, "avg_precision": 0.7, "avg_recall": 0.7, "avg_latency_ms": 50.0},
            "c": {"avg_accuracy": 0.5, "avg_precision": 0.6, "avg_recall": 0.6, "avg_latency_ms": 10.0},
        }
    }

    w1 = fim.compute_confidence_weights(metrics)
    w2 = fim.compute_confidence_weights(metrics)
    # Deterministic
    assert w1 == w2
    # Weights sum to ~1
    assert abs(sum(w1.values()) - 1.0) < 1e-9


def test_collect_and_aggregate(tmp_path: Path):
    # Create two fake instances with learning metrics
    inst1 = tmp_path / "inst1"
    inst2 = tmp_path / "inst2"
    (inst1 / "logs").mkdir(parents=True)
    (inst2 / "logs").mkdir(parents=True)

    (inst1 / "logs" / "learning_metrics.jsonl").write_text(
        "\n".join([
            "{""metric"": ""accuracy"", ""value"": 0.9}",
            "{""metric"": ""precision"", ""value"": 0.8}",
            "{""metric"": ""recall"", ""value"": 0.85}",
            "{""metric"": ""latency"", ""value"": 120}",
        ])
    )
    (inst2 / "logs" / "learning_metrics.jsonl").write_text(
        "\n".join([
            "{""metric"": ""accuracy"", ""value"": 0.7}",
            "{""metric"": ""precision"", ""value"": 0.75}",
            "{""metric"": ""recall"", ""value"": 0.7}",
            "{""metric"": ""latency"", ""value"": 80}",
        ])
    )

    hub = InstanceHub()
    hub.register_instance("inst1", inst1)
    hub.register_instance("inst2", inst2)

    fim = FederatedIntelligenceManager(hub)
    metrics = fim.collect_federated_metrics()
    weights = fim.compute_confidence_weights(metrics)

    assert set(metrics["instances"].keys()) == {"inst1", "inst2"}
    assert 0.0 <= weights["inst1"] <= 1.0
    assert 0.0 <= weights["inst2"] <= 1.0
    assert abs(weights["inst1"] + weights["inst2"] - 1.0) < 1e-9


