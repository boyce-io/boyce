import time
from datashark_mcp.context.graph_builder import GraphBuilder
from datashark_mcp.context.store.memory_store import MemoryStore
from datashark_mcp.context.api import ContextAPI
from datashark_mcp.reasoning.benchmark import benchmark_reasoning


def _artifact(system: str, atype: str, name: str, **kwargs):
    a = {"system": system, "type": atype, "name": name}
    a.update(kwargs)
    return a


def test_reasoning_benchmark_latency_under_300ms():
    gb = GraphBuilder()
    artifacts = [
        _artifact("looker", "entity", "A"),
        _artifact("looker", "entity", "B"),
        _artifact("looker", "entity", "C"),
        _artifact("looker", "relationship", "A_B", attributes={"left": "A", "right": "B", "keys": [{"left": "id", "right": "id"}]}),
        _artifact("looker", "relationship", "B_C", attributes={"left": "B", "right": "C", "keys": [{"left": "id", "right": "id"}]}),
    ]
    nodes, edges = gb.build(artifacts)
    ms = MemoryStore()
    ms.load(nodes, edges)
    # add some salience
    ms.set_salience({nodes[0].id: 0.8, nodes[1].id: 0.6, nodes[2].id: 0.4})
    ctx = ContextAPI(ms)

    question = {"from": [nodes[0].id, nodes[2].id], "select": ["A.id"]}
    t0 = time.perf_counter()
    res = benchmark_reasoning(question, ctx)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert res["total_path_depth"] >= 2
    assert elapsed_ms < 300.0

# === Phase 8: Cross-Table Reasoning Benchmarks ===
from datashark_mcp.reasoning.benchmark import benchmark_reasoning as run_bench


def test_multitable_queries():
    """Evaluate multi-table NL→SQL join performance and correctness."""
    sample_questions = [
        "total revenue by region for the last 90 days",
        "daily sales by product category in California for the past six months",
        "average order value per customer by region this quarter",
        "top 5 products by total sales and conversion rate",
        "total orders by marketing campaign and channel for September",
    ]
    metrics = run_bench("looker", questions=sample_questions)
    print("✅ Phase 8 multi-table benchmark metrics:")
    print(metrics)
    assert metrics["nl_to_sql_accuracy"] >= 0.9
    assert metrics["avg_latency_ms"] < 500

