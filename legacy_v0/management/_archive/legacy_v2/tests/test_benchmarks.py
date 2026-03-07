"""
Benchmark Tests

Runs downsized benchmarks for CI with scaled thresholds.
"""

import pytest
import json
from datashark_mcp.context.benchmarks import run_benchmarks


def test_benchmarks_meet_scaled_budgets():
    """Run benchmarks on downsized graph and verify scaled budgets."""
    # Smaller graph for CI
    num_nodes = 10000
    num_edges = 20000
    
    results = run_benchmarks(num_nodes, num_edges, seed=42)
    
    # Scaled budgets (more lenient for smaller graph)
    budgets = {
        "get_node": 1.0,
        "search": 10.0,
        "bfs_single_source": 60.0,  # Scaled from 100ms
        "bfs_cross_system": 60.0,  # Scaled from 100ms
        "semantic_enrichment": 300.0,  # Scaled for 10k nodes
        "dsl_query": 30.0,
        "nl_translation": 50.0,
        "reasoning_execution": 200.0,
        "explanation_rendering": 100.0,
    }
    
    failed = []
    for result in results:
        budget = budgets.get(result.op)
        if budget:
            if result.p95_ms > budget:
                failed.append(f"{result.op}: p95 {result.p95_ms:.3f}ms > {budget}ms")
    
    if failed:
        pytest.fail(f"Budget violations:\n" + "\n".join(failed))
    
    # Output results as JSON for CI
    for result in results:
        print(json.dumps(result.to_json()))

