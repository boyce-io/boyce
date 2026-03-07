from datashark_mcp.context.graph_builder import GraphBuilder
from datashark_mcp.context.store.memory_store import MemoryStore
from datashark_mcp.context.api import ContextAPI
from datashark_mcp.reasoning.nl_parser import parse_question, normalize_date_range


def _artifact(system: str, atype: str, name: str, **kwargs):
    a = {"system": system, "type": atype, "name": name}
    a.update(kwargs)
    return a


def _ctx():
    gb = GraphBuilder()
    nodes, edges = gb.build([
        _artifact("looker", "entity", "Beastie Boys"),
        _artifact("looker", "entity", "US"),
    ])
    ms = MemoryStore()
    ms.load(nodes, edges)
    # seed salience
    ms.set_salience({nodes[0].id: 0.9, nodes[1].id: 0.7})
    return ContextAPI(ms)


def test_parse_question_extracts_metric_and_time():
    ctx = _ctx()
    q = "daily view total of the Beastie Boys in the US for the past six months"
    out = parse_question(q, ctx)
    plan = out["plan"]
    assert "total" in plan["select"]
    assert "day" in plan.get("group_by", [])
    assert any("RELATIVE:-6 month" in f or "RELATIVE:-6 months" in f for f in plan.get("filters", []))


def test_normalize_date_range_variants():
    tr = normalize_date_range("past 3 weeks")
    assert tr["gte"].startswith("RELATIVE:-3 week")

