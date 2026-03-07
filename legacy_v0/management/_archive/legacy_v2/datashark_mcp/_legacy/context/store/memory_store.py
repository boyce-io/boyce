from __future__ import annotations

from typing import Dict, List, Optional
from datashark_mcp.context.schema import Node, Edge
import copy


class MemoryStore:
    def __init__(self) -> None:
        self._nodes: Dict[str, Node] = {}
        self._edges: Dict[str, Edge] = {}
        self._salience: Dict[str, float] = {}

    def load(self, nodes: List[Node], edges: List[Edge]) -> None:
        self._nodes = {n.id: n for n in nodes}
        self._edges = {e.id: e for e in edges}

    def nodes(self) -> List[Node]:
        return [copy.deepcopy(n) for n in self._nodes.values()]

    def edges(self) -> List[Edge]:
        return [copy.deepcopy(e) for e in self._edges.values()]

    def get_node(self, node_id: str) -> Node | None:
        n = self._nodes.get(node_id)
        return copy.deepcopy(n) if n else None

    def get_edge(self, edge_id: str) -> Edge | None:
        e = self._edges.get(edge_id)
        return copy.deepcopy(e) if e else None

    # Salience cache
    def set_salience(self, mapping: Dict[str, float]) -> None:
        self._salience = dict(mapping)

    def get_salience(self, _id: str) -> float:
        return float(self._salience.get(_id, 0.0))

    def top_salience(self, top_n: int = 10) -> List[tuple[str, float]]:
        items = sorted(self._salience.items(), key=lambda x: (-x[1], x[0]))
        return items[: max(0, top_n)]
