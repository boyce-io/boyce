from datashark_mcp.context.graph_builder import GraphBuilder
from datashark_mcp.context.store.memory_store import MemoryStore
from datashark_mcp.context.api import ContextAPI
from datashark_mcp.reasoning.nl_parser import parse_question


def _artifact(system: str, atype: str, name: str, **kwargs):
    a = {"system": system, "type": atype, "name": name}
    a.update(kwargs)
    return a


def test_canned_nl_queries_produce_plans():
    gb = GraphBuilder()
    nodes, edges = gb.build([
        _artifact("looker", "entity", "Beastie Boys"),
        _artifact("looker", "entity", "US"),
        _artifact("looker", "entity", "views"),
    ])
    ms = MemoryStore()
    ms.load(nodes, edges)
    ms.set_salience({n.id: 0.7 for n in nodes})
    ctx = ContextAPI(ms)

    queries = [
        "daily view total of the Beastie Boys in the US for the past six months",
        "count of views in US past 3 months",
    ]
    for q in queries:
        out = parse_question(q, ctx)
        assert out["plan"]["select"]
        assert out["confidence"] >= 0.5

