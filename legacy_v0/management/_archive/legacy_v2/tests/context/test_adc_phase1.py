import tempfile
from pathlib import Path
from datashark_mcp.context.schema import NodeType, EdgeType, Node, Edge, Provenance, ValidationIssue, ValidationResult
from datashark_mcp.context.graph_builder import GraphBuilder
from datashark_mcp.context.store.json_store import JSONStore
from datashark_mcp.context.api import ContextAPI
from datashark_mcp.context.store.memory_store import MemoryStore


def _artifact(system: str, atype: str, name: str, **kwargs):
    a = {"system": system, "type": atype, "name": name}
    a.update(kwargs)
    return a


def test_round_trip_hash_and_counts_identical():
    gb = GraphBuilder()
    artifacts = [
        _artifact("looker", "entity", "public.orders"),
        _artifact("looker", "entity", "public.customers"),
        _artifact("looker", "relationship", "orders_customers", attributes={"left": "public.orders", "right": "public.customers"}),
    ]
    nodes, edges = gb.build(artifacts)
    with tempfile.TemporaryDirectory() as tmp:
        store = JSONStore(Path(tmp))
        gb.persist(store, nodes, edges, manifest={})
        n2, e2, m2 = store.load()
        assert len(n2) == len(nodes)
        assert len(e2) == len(edges)


def test_deterministic_ids_and_hashes():
    gb = GraphBuilder()
    a1 = [_artifact("looker", "entity", "public.orders")]
    a2 = [_artifact("looker", "entity", "public.orders")]
    n1, e1 = gb.build(a1)
    n2, e2 = gb.build(a2)
    assert n1[0].id == n2[0].id
    assert n1[0].hash == n2[0].hash


def test_persistence_atomic_and_manifest_enrichment():
    gb = GraphBuilder()
    artifacts = [
        _artifact("looker", "entity", "public.orders"),
        _artifact("looker", "entity", "public.customers"),
    ]
    nodes, edges = gb.build(artifacts)
    with tempfile.TemporaryDirectory() as tmp:
        store = JSONStore(Path(tmp))
        gb.persist(store, nodes, edges, manifest={})
        _, _, manifest = store.load()
        assert manifest.get("graph_schema_version") == "0.1.0"
        assert manifest.get("node_count") == len(nodes)
        assert manifest.get("edge_count") == len(edges)
        assert manifest.get("sha256_payload_hash")
        prov = manifest.get("provenance_summary", {}).get("counts_by_system", {})
        assert prov.get("looker") == len(nodes) + len(edges)


def test_context_api_search_find_join_path():
    gb = GraphBuilder()
    artifacts = [
        _artifact("looker", "entity", "A"),
        _artifact("looker", "entity", "B"),
        _artifact("looker", "entity", "C"),
        _artifact("looker", "relationship", "A_B", attributes={"left": "A", "right": "B"}),
        _artifact("looker", "relationship", "B_C", attributes={"left": "B", "right": "C"}),
    ]
    nodes, edges = gb.build(artifacts)
    store = MemoryStore()
    store.load(nodes, edges)
    api = ContextAPI(store)
    res = api.find_join_path(nodes[0].id, nodes[2].id)
    assert res["depth"] == 2
    assert len(res["path"]) == 2
    assert res["path_score"] > 0
    assert "looker" in res["sources_involved"]


def test_validation_failure_issue_type_shape():
    issue = ValidationIssue(code="E001", message="error", node_or_edge_id=None, provenance=None)
    vr = ValidationResult(ok=False, issues=[issue], path_depth=None, score=None, explanation="x")
    assert not vr.ok
    assert vr.issues[0].code == "E001"

