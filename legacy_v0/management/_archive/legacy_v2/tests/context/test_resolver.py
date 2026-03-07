from datashark_mcp.context.graph_builder import GraphBuilder
from datashark_mcp.context.store.memory_store import MemoryStore
from datashark_mcp.context.api import ContextAPI


def _artifact(system: str, atype: str, name: str, **kwargs):
    a = {"system": system, "type": atype, "name": name}
    a.update(kwargs)
    return a


def test_resolve_entity_confidence_and_id_mapping():
    gb = GraphBuilder()
    nodes, edges = gb.build([
        _artifact("looker", "entity", "Beastie Boys"),
        _artifact("looker", "entity", "US"),
    ])
    ms = MemoryStore()
    ms.load(nodes, edges)
    # salience boosts
    ms.set_salience({nodes[0].id: 0.8, nodes[1].id: 0.4})
    ctx = ContextAPI(ms)

    r = ctx.resolve_entity("Beastie Boys")
    assert r and r["id"] == nodes[0].id and r["confidence"] > 0.5

