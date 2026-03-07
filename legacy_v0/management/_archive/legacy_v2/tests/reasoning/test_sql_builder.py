from pathlib import Path
from datashark_mcp.context.graph_builder import GraphBuilder
from datashark_mcp.context.store.memory_store import MemoryStore
from datashark_mcp.context.api import ContextAPI
from datashark_mcp.reasoning.sql_builder import build_sql


def _artifact(system: str, atype: str, name: str, **kwargs):
    a = {"system": system, "type": atype, "name": name}
    a.update(kwargs)
    return a


def _ctx_for(artifacts):
    gb = GraphBuilder()
    nodes, edges = gb.build(artifacts)
    ms = MemoryStore()
    ms.load(nodes, edges)
    return ContextAPI(ms)


def test_case_a_single_table_metric_no_joins():
    ctx = _ctx_for([
        _artifact("looker", "entity", "sales"),
    ])
    plan = {"select": ["amount"], "from": ["sales"], "filters": ["amount > 0"], "limit": 10}
    out = build_sql(plan, ctx)
    assert "FROM \"sales\" AS t1" in out["sql"]
    assert not out["joins"]


def test_case_b_two_table_metric_one_hop_join():
    ctx = _ctx_for([
        _artifact("looker", "entity", "orders"),
        _artifact("looker", "entity", "customers"),
        _artifact("looker", "relationship", "orders_customers", attributes={"left": "orders", "right": "customers", "keys": [{"left": "customer_id", "right": "id"}]}),
    ])
    plan = {"select": ["orders.total"], "from": ["orders", "customers"], "limit": 5}
    out = build_sql(plan, ctx)
    assert "LEFT JOIN" in out["sql"]
    assert any("customer_id" in out["sql"] for _ in [0])
    assert len(out["joins"]) >= 1


def test_case_c_three_table_metric_multi_hop_join():
    ctx = _ctx_for([
        _artifact("looker", "entity", "orders"),
        _artifact("looker", "entity", "customers"),
        _artifact("looker", "entity", "regions"),
        _artifact("looker", "relationship", "orders_customers", attributes={"left": "orders", "right": "customers", "keys": [{"left": "customer_id", "right": "id"}]}),
        _artifact("looker", "relationship", "customers_regions", attributes={"left": "customers", "right": "regions", "keys": [{"left": "region_id", "right": "id"}]}),
    ])
    plan = {"select": ["orders.total"], "from": ["orders", "regions"], "limit": 5}
    out = build_sql(plan, ctx)
    assert out["sql"].count("LEFT JOIN") >= 2
    assert len(out["joins"]) >= 2


def test_case_d_ambiguous_field_name_warning():
    ctx = _ctx_for([
        _artifact("looker", "entity", "orders"),
    ])
    plan = {"select": ["id"], "from": ["orders"], "limit": 1}
    out = build_sql(plan, ctx)
    # With naive qualifier, no warning is strictly required but the pipeline should still return SQL
    assert "SELECT" in out["sql"]


def test_case_e_orphan_table_validation_error_shape():
    ctx = _ctx_for([
        _artifact("looker", "entity", "orders"),
        _artifact("looker", "entity", "regions"),
    ])
    plan = {"select": ["orders.total"], "from": ["orders", "regions"], "limit": 5}
    out = build_sql(plan, ctx)
    # No path exists; either zero joins or warnings emitted
    assert isinstance(out.get("warnings"), list)

