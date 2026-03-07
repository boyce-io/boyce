from __future__ import annotations

from typing import List, Dict, Any, Set, Tuple

from datashark_mcp.kernel.air_gap_api import AirGapAPI


def plan_joins(tables: List[str], ctx: AirGapAPI) -> List[Dict[str, Any]]:
    """
    Greedy Steiner-approx: connect all tables by repeatedly unioning shortest
    paths between the current tree and the farthest remaining table using
    AirGapAPI.find_join_path (BFS over relationships).

    Returns ordered list of join edges with default join_type='LEFT'.
    Each join dict: {left, right, keys, join_type, path_depth, sources_involved}
    """
    if not tables or len(tables) == 1:
        return []

    # Initialize with the first table
    connected: Set[str] = {tables[0]}
    remaining: Set[str] = set(tables[1:])
    planned: List[Dict[str, Any]] = []

    # Helper to path -> join dicts
    def edges_from_path(path_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        joins: List[Dict[str, Any]] = []
        # path_info["path"] contains relationship dictionaries from AirGapAPI
        for rel in path_info.get("path", []):
            # Extract source and target from relationship dict
            source = rel.get("source_entity_id") or rel.get("source") or rel.get("from")
            target = rel.get("target_entity_id") or rel.get("target") or rel.get("to")
            # Extract join keys from relationship dict
            keys = rel.get("keys") or rel.get("join_keys") or []
            joins.append({
                "left": source,
                "right": target,
                "keys": keys,
                "join_type": "LEFT",
                "path_depth": path_info.get("depth", 1),
                "sources_involved": path_info.get("sources_involved", []),
            })
        return joins

    while remaining:
        best: Tuple[int, float, str, Dict[str, Any]] | None = None
        # Pick a remaining table that has the best (shortest) path from any connected node
        for target in list(remaining):
            candidate = None
            for src in connected:
                path_info = ctx.find_join_path(src, target)
                if path_info is None:
                    continue
                depth = path_info.get("depth", 0)
                score = path_info.get("path_score", 0.0)
                if depth == 0:
                    continue
                tup = (depth, -score, src, path_info)
                if candidate is None or tup < candidate:
                    candidate = tup
            if candidate is not None:
                if best is None or candidate < best:
                    best = candidate
        if best is None:
            # No path found for one or more remaining tables; stop and return what we have
            break
        depth, _neg_score, src, path_info = best
        # Add path edges to plan
        planned.extend(edges_from_path(path_info))
        # Mark all nodes in the path as connected
        path_list = path_info.get("path", [])
        if path_list:
            # Get source from first relationship
            first_rel = path_list[0]
            first_source = first_rel.get("source_entity_id") or first_rel.get("source") or first_rel.get("from")
            connected.add(first_source if first_source else src)
            # Add all targets from relationships
            for rel in path_list:
                target = rel.get("target_entity_id") or rel.get("target") or rel.get("to")
                if target:
                    connected.add(target)
        else:
            connected.add(src)
        # Remove any remaining tables that are now connected
        remaining = {t for t in remaining if t not in connected}

    # Deduplicate while preserving order (by left+right)
    seen: Set[Tuple[str, str]] = set()
    ordered: List[Dict[str, Any]] = []
    for j in planned:
        key = (j["left"], j["right"])
        if key in seen:
            continue
        seen.add(key)
        ordered.append(j)
    return ordered


