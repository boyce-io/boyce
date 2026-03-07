"""
Merge Semantics

Implements upsert and tombstone merge logic as defined in Merge Semantics section.
Respects provenance timestamps and extractor_version precedence.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple
from datashark_mcp.context.models import Node, Edge
from datashark_mcp.context.store import GraphStore


def parse_iso8601(iso_str: str) -> datetime:
    """Parse ISO 8601 timestamp string."""
    # Handle with or without microseconds
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except ValueError:
        # Fallback for formats without timezone
        return datetime.fromisoformat(iso_str)


def merge_node(
    existing: Optional[Node],
    new: Node,
    store: GraphStore
) -> Tuple[Node, str]:
    """
    Merge new node with existing node using conflict resolution rules.
    
    Conflict Resolution:
    1. If existing is None, return new (status="new")
    2. If extracted_at differs, prefer newest
    3. If extracted_at equal, prefer lexicographically greater extractor_version
    4. Preserve last writer's provenance
    
    Args:
        existing: Existing node in store (or None)
        new: New node to merge
        store: GraphStore instance
        
    Returns:
        Tuple of (merged_node, status) where status is "new", "changed", or "unchanged"
    """
    if existing is None:
        store.add_node(new)
        return new, "new"
    
    if existing.id != new.id:
        raise ValueError(f"ID mismatch: existing={existing.id}, new={new.id}")
    
    # Conflict resolution
    existing_time = parse_iso8601(existing.provenance.extracted_at)
    new_time = parse_iso8601(new.provenance.extracted_at)
    
    should_update = False
    
    if new_time > existing_time:
        # Newer timestamp wins
        should_update = True
    elif new_time == existing_time:
        # Same timestamp, check extractor version
        existing_version = existing.provenance.extractor_version or ""
        new_version = new.provenance.extractor_version or ""
        if new_version > existing_version:
            # Lexicographically greater version wins
            should_update = True
    
    if should_update:
        # Update with new node (preserves new provenance)
        store.add_node(new)
        return new, "changed"
    else:
        # Keep existing
        return existing, "unchanged"


def merge_edge(
    existing: Optional[Edge],
    new: Edge,
    store: GraphStore
) -> Tuple[Edge, str]:
    """
    Merge new edge with existing edge using conflict resolution rules.
    
    Same conflict resolution as merge_node.
    
    Args:
        existing: Existing edge in store (or None)
        new: New edge to merge
        store: GraphStore instance
        
    Returns:
        Tuple of (merged_edge, status) where status is "new", "changed", or "unchanged"
    """
    if existing is None:
        store.add_edge(new)
        return new, "new"
    
    if existing.id != new.id:
        raise ValueError(f"ID mismatch: existing={existing.id}, new={new.id}")
    
    # Conflict resolution
    existing_time = parse_iso8601(existing.provenance.extracted_at)
    new_time = parse_iso8601(new.provenance.extracted_at)
    
    should_update = False
    
    if new_time > existing_time:
        should_update = True
    elif new_time == existing_time:
        existing_version = existing.provenance.extractor_version or ""
        new_version = new.provenance.extractor_version or ""
        if new_version > existing_version:
            should_update = True
    
    if should_update:
        store.add_edge(new)
        return new, "changed"
    else:
        return existing, "unchanged"


class MergeResult:
    """Result of a merge operation with counts."""
    
    def __init__(self) -> None:
        self.new_nodes: int = 0
        self.changed_nodes: int = 0
        self.new_edges: int = 0
        self.changed_edges: int = 0
        self.deleted_nodes: int = 0
        self.deleted_edges: int = 0
    
    def to_dict(self) -> Dict[str, int]:
        """Convert to dict for telemetry."""
        return {
            "new_nodes": self.new_nodes,
            "changed_nodes": self.changed_nodes,
            "new_edges": self.new_edges,
            "changed_edges": self.changed_edges,
            "deleted_nodes": self.deleted_nodes,
            "deleted_edges": self.deleted_edges,
        }


def merge_nodes_and_edges(
    nodes: List[Node],
    edges: List[Edge],
    store: GraphStore,
    handle_deletions: bool = False
) -> MergeResult:
    """
    Merge lists of nodes and edges into the store.
    
    Args:
        nodes: List of nodes to merge
        edges: List of edges to merge
        store: GraphStore instance
        handle_deletions: If True, mark missing nodes/edges as deleted (tombstones)
        
    Returns:
        MergeResult with counts
    """
    result = MergeResult()
    
    # Track which nodes/edges we've seen
    seen_node_ids: set[str] = set()
    seen_edge_ids: set[str] = set()
    
    # Merge nodes
    for node in nodes:
        seen_node_ids.add(node.id)
        existing = store.get_node(node.id)
        merged, status = merge_node(existing, node, store)
        if status == "new":
            result.new_nodes += 1
        elif status == "changed":
            result.changed_nodes += 1
    
    # Merge edges
    for edge in edges:
        seen_edge_ids.add(edge.id)
        existing = store.get_edge(edge.id)
        merged, status = merge_edge(existing, edge, store)
        if status == "new":
            result.new_edges += 1
        elif status == "changed":
            result.changed_edges += 1
    
    # Handle deletions (tombstones)
    if handle_deletions:
        # Find nodes that exist in store but not in new list
        all_store_node_ids = store.get_all_node_ids()
        deleted_node_ids = all_store_node_ids - seen_node_ids
        
        for node_id in deleted_node_ids:
            node = store.get_node(node_id)
            if node and not node.deleted_at:
                # Create tombstone
                from datetime import datetime, timezone
                tombstone = Node(
                    id=node.id,
                    system=node.system,
                    type=node.type,
                    name=node.name,
                    attributes=node.attributes,
                    provenance=node.provenance,
                    repo=node.repo,
                    schema=node.schema,
                    deleted_at=datetime.now(timezone.utc).isoformat()
                )
                store.add_node(tombstone)
                result.deleted_nodes += 1
        
        # Find edges that exist in store but not in new list
        all_store_edge_ids = store.get_all_edge_ids()
        deleted_edge_ids = all_store_edge_ids - seen_edge_ids
        
        for edge_id in deleted_edge_ids:
            edge = store.get_edge(edge_id)
            if edge and not edge.deleted_at:
                # Create tombstone
                from datetime import datetime, timezone
                tombstone = Edge(
                    id=edge.id,
                    src=edge.src,
                    dst=edge.dst,
                    type=edge.type,
                    attributes=edge.attributes,
                    provenance=edge.provenance,
                    deleted_at=datetime.now(timezone.utc).isoformat()
                )
                store.add_edge(tombstone)
                result.deleted_edges += 1
    
    return result

