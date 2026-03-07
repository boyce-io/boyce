import json

from datashark_mcp.context import schema
from datashark_mcp.context.schema import NodeType, Node
from datashark_mcp.context.graph_builder import GraphBuilder
from datashark_mcp.context.store.memory_store import MemoryStore
from datashark_mcp.context.api import ContextAPI
from datashark_mcp.heuristics import salience
from datashark_mcp.reasoning import nl_parser, benchmark


def test_stable_ids_and_hashes():
    a = schema.stable_node_id("sys", NodeType.ENTITY, "customers")
    b = schema.stable_node_id("sys", NodeType.ENTITY, "customers")
    c = schema.stable_node_id("sys", NodeType.ENTITY, "orders")
    assert a == b
    assert a != c

    n = Node(id="x", type=NodeType.ENTITY, system="sys", name="a")
    h1 = schema.compute_node_hash(n)
    h2 = schema.compute_node_hash(n)
    assert h1 == h2


def test_graph_builder_node_edge_integrity():
    gb = GraphBuilder()
    raw = [
        {"system": "t", "type": "entity", "name": "customers"},
        {"system": "t", "type": "entity", "name": "orders"},
        {"system": "t", "type": "relationship", "name": "c_o", "attributes": {"left": "customers", "right": "orders"}},
    ]
    nodes, edges = gb.build(raw)
    node_ids = {n.id for n in nodes}
    assert nodes and edges
    for e in edges:
        assert e.src in node_ids and e.dst in node_ids


def test_salience_determinism():
    usage = {"a": {"query_frequency": 0.0, "dashboard_refs": 0.0, "lineage_count": 1.0},
             "b": {"query_frequency": 0.0, "dashboard_refs": 0.0, "lineage_count": 2.0}}
    s1 = salience.compute_salience(usage)
    s2 = salience.compute_salience(usage)
    assert s1.keys() == s2.keys()
    for k in s1:
        assert abs(s1[k].score - s2[k].score) < 1e-9
        assert 0.0 <= s1[k].score <= 1.0


def _ctx_with_entities(names):
    gb = GraphBuilder()
    raw = [{"system": "looker", "type": "entity", "name": nm} for nm in names]
    nodes, edges = gb.build(raw)
    ms = MemoryStore()
    ms.load(nodes, edges)
    # seed simple salience
    ms.set_salience({nodes[0].id: 0.9})
    return ContextAPI(ms)


def test_nl_parser_date_normalization():
    ctx = _ctx_with_entities(["revenue", "US", "Beastie Boys"])
    q = "daily revenue for the past six months"
    out = nl_parser.parse_question(q, ctx)
    rng = nl_parser.normalize_date_range("past six months")
    assert "plan" in out and isinstance(rng, dict)
    assert "gte" in rng and "lte" in rng


def test_benchmark_metrics_structure():
    m = benchmark.benchmark_reasoning("looker", questions=["total revenue by region"])
    keys = {"nl_to_sql_accuracy", "avg_latency_ms", "avg_path_depth", "salience_sum", "count"}
    assert keys.issubset(set(m.keys()))


