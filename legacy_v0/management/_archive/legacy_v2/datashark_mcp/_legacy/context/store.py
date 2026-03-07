"""
Graph Store Implementation

Provides GraphStore with query methods matching the enterprise spec.
Backed by in-memory dicts with hooks for future persistent backends.
"""

from __future__ import annotations

import copy
from collections import defaultdict, deque
from typing import Dict, List, Optional, Set, Deque, Tuple
from datashark_mcp.context.models import Node, Edge


class GraphStore:
    """
    In-memory graph store with query capabilities.
    
    Supports:
    - add_node, add_edge
    - get_node, get_edge
    - find_entities_by_system
    - find_entities_by_repo
    - search with filters
    - find_join_paths_from (BFS)
    """
    
    def __init__(self) -> None:
        """Initialize empty graph store."""
        # Core storage
        self._nodes: Dict[str, Node] = {}
        self._edges: Dict[str, Edge] = {}
        
        # Indexes for fast lookups
        self._by_system: Dict[str, List[str]] = defaultdict(list)  # system -> [node_ids]
        self._by_repo: Dict[str, List[str]] = defaultdict(list)    # repo -> [node_ids]
        self._by_schema: Dict[str, List[str]] = defaultdict(list)  # schema -> [node_ids]
        self._by_name: Dict[str, str] = {}  # name -> node_id (first match)
        
        # Edge indexes
        self._edges_by_src: Dict[str, List[str]] = defaultdict(list)  # src_id -> [edge_ids]
        self._edges_by_dst: Dict[str, List[str]] = defaultdict(list)  # dst_id -> [edge_ids]
        self._edges_by_type: Dict[str, List[str]] = defaultdict(list)  # edge_type -> [edge_ids]
    
    def add_node(self, node: Node) -> None:
        """
        Add or update a node in the store.
        
        Args:
            node: Node to add/update
        """
        node_id = node.id
        
        # Remove from old indexes if updating
        if node_id in self._nodes:
            old_node = self._nodes[node_id]
            self._remove_node_from_indexes(old_node)
        
        # Add to store
        self._nodes[node_id] = node
        
        # Update indexes
        self._index_node(node)
    
    def _remove_node_from_indexes(self, node: Node) -> None:
        """Remove node from all indexes."""
        if node.system in self._by_system:
            self._by_system[node.system] = [nid for nid in self._by_system[node.system] if nid != node.id]
        if node.repo and node.repo in self._by_repo:
            self._by_repo[node.repo] = [nid for nid in self._by_repo[node.repo] if nid != node.id]
        if node.schema and node.schema in self._by_schema:
            self._by_schema[node.schema] = [nid for nid in self._by_schema[node.schema] if nid != node.id]
        if node.name in self._by_name and self._by_name[node.name] == node.id:
            del self._by_name[node.name]
    
    def _index_node(self, node: Node) -> None:
        """Add node to all indexes."""
        node_id = node.id
        
        # Index by system
        if node_id not in self._by_system[node.system]:
            self._by_system[node.system].append(node_id)
        
        # Index by repo
        if node.repo:
            if node_id not in self._by_repo[node.repo]:
                self._by_repo[node.repo].append(node_id)
        
        # Index by schema
        if node.schema:
            if node_id not in self._by_schema[node.schema]:
                self._by_schema[node.schema].append(node_id)
        
        # Index by name (first match wins)
        if node.name not in self._by_name:
            self._by_name[node.name] = node_id
    
    def add_edge(self, edge: Edge) -> None:
        """
        Add or update an edge in the store.
        
        Args:
            edge: Edge to add/update
        """
        edge_id = edge.id
        
        # Remove from old indexes if updating
        if edge_id in self._edges:
            old_edge = self._edges[edge_id]
            self._remove_edge_from_indexes(old_edge)
        
        # Add to store
        self._edges[edge_id] = edge
        
        # Update indexes
        self._index_edge(edge)
    
    def _remove_edge_from_indexes(self, edge: Edge) -> None:
        """Remove edge from all indexes."""
        if edge.src in self._edges_by_src:
            self._edges_by_src[edge.src] = [eid for eid in self._edges_by_src[edge.src] if eid != edge.id]
        if edge.dst in self._edges_by_dst:
            self._edges_by_dst[edge.dst] = [eid for eid in self._edges_by_dst[edge.dst] if eid != edge.id]
        if edge.type in self._edges_by_type:
            self._edges_by_type[edge.type] = [eid for eid in self._edges_by_type[edge.type] if eid != edge.id]
    
    def _index_edge(self, edge: Edge) -> None:
        """Add edge to all indexes."""
        edge_id = edge.id
        
        # Index by source
        if edge_id not in self._edges_by_src[edge.src]:
            self._edges_by_src[edge.src].append(edge_id)
        
        # Index by destination
        if edge_id not in self._edges_by_dst[edge.dst]:
            self._edges_by_dst[edge.dst].append(edge_id)
        
        # Index by type
        if edge_id not in self._edges_by_type[edge.type]:
            self._edges_by_type[edge.type].append(edge_id)
    
    def get_node(self, node_id: str) -> Optional[Node]:
        """
        Get node by ID (immutable copy).
        
        Args:
            node_id: Node ID
            
        Returns:
            Deep copy of node, or None if not found
        """
        node = self._nodes.get(node_id)
        return copy.deepcopy(node) if node else None
    
    def get_edge(self, edge_id: str) -> Optional[Edge]:
        """
        Get edge by ID (immutable copy).
        
        Args:
            edge_id: Edge ID
            
        Returns:
            Deep copy of edge, or None if not found
        """
        edge = self._edges.get(edge_id)
        return copy.deepcopy(edge) if edge else None
    
    def find_entities_by_system(self, system: str) -> List[Node]:
        """
        Find all entities for a given system.
        
        Args:
            system: System identifier
            
        Returns:
            List of entity nodes (type=ENTITY) with system=system (immutable copies)
        """
        node_ids = self._by_system.get(system, [])
        results = []
        for node_id in node_ids:
            node = self._nodes.get(node_id)
            if node and node.type == "ENTITY" and not node.deleted_at:
                results.append(copy.deepcopy(node))
        return results
    
    def find_entities_by_repo(self, repo: str) -> List[Node]:
        """
        Find all entities for a given repository.
        
        Args:
            repo: Repository identifier
            
        Returns:
            List of entity nodes (type=ENTITY) with repo=repo (immutable copies)
        """
        node_ids = self._by_repo.get(repo, [])
        results = []
        for node_id in node_ids:
            node = self._nodes.get(node_id)
            if node and node.type == "ENTITY" and not node.deleted_at:
                results.append(copy.deepcopy(node))
        return results
    
    def search(
        self,
        term: str,
        filters: Optional[Dict[str, List[str]]] = None
    ) -> List[Node]:
        """
        Search entities by name/term with optional filters.
        
        Args:
            term: Search term (matched against node.name)
            filters: Optional dict with keys: "system", "repo", "schema"
                Each value is a list of allowed values
                
        Returns:
            List of matching nodes (immutable copies)
        """
        term_lower = term.lower()
        results = []
        
        # Apply filters first to get candidate set
        candidate_ids: Set[str] = set()
        
        if filters:
            # Filter by system
            if "system" in filters:
                for system in filters["system"]:
                    candidate_ids.update(self._by_system.get(system, []))
            
            # Filter by repo
            if "repo" in filters:
                for repo in filters["repo"]:
                    candidate_ids.update(self._by_repo.get(repo, []))
            
            # Filter by schema
            if "schema" in filters:
                for schema in filters["schema"]:
                    candidate_ids.update(self._by_schema.get(schema, []))
            
            # If no filters, use all nodes
            if not candidate_ids:
                candidate_ids = set(self._nodes.keys())
        else:
            candidate_ids = set(self._nodes.keys())
        
        # Search in candidates
        for node_id in candidate_ids:
            node = self._nodes.get(node_id)
            if not node or node.deleted_at:
                continue
            
            # Match term against name
            if term_lower in node.name.lower():
                # Check additional filters
                if filters:
                    if "system" in filters and node.system not in filters["system"]:
                        continue
                    if "repo" in filters:
                        repo = node.repo
                        if not repo or repo not in filters["repo"]:
                            continue
                    if "schema" in filters:
                        schema = node.schema
                        if not schema or schema not in filters["schema"]:
                            continue
                
                results.append(copy.deepcopy(node))
        
        return results
    
    def find_join_paths_from(
        self,
        node_id: str,
        max_depth: int = 5
    ) -> List[Dict[str, any]]:
        """
        Find all join paths from a given node using BFS.
        
        Args:
            node_id: Source node ID
            max_depth: Maximum path depth to search
            
        Returns:
            List of path dicts, each containing:
            - path: List[Edge] (edges in path)
            - depth: int (number of hops)
            - path_score: float (quality heuristic: 1/depth)
            - sources_involved: List[str] (systems in path)
        """
        if node_id not in self._nodes:
            return []
        
        # Build adjacency list for JOINS_TO edges
        edges = [e for e in self._edges.values() if e.type == "JOINS_TO" and not e.deleted_at]
        adj: Dict[str, List[Edge]] = defaultdict(list)
        for edge in edges:
            adj[edge.src].append(edge)
        
        # BFS with depth limit
        paths: List[Dict[str, any]] = []
        queue: Deque[Tuple[str, List[Edge], Set[str]]] = deque()
        visited: Set[str] = set()
        
        queue.append((node_id, [], set()))
        visited.add(node_id)
        
        while queue:
            current_id, path, sources = queue.popleft()
            current_depth = len(path)
            
            if current_depth > 0:
                # Record this path
                paths.append({
                    "path": [copy.deepcopy(e) for e in path],
                    "depth": current_depth,
                    "path_score": 1.0 / current_depth if current_depth > 0 else 1.0,
                    "sources_involved": sorted(sources),
                })
            
            if current_depth >= max_depth:
                continue
            
            # Explore neighbors
            for edge in adj.get(current_id, []):
                next_id = edge.dst
                if next_id not in visited:
                    visited.add(next_id)
                    new_sources = sources.copy()
                    if edge.provenance and edge.provenance.system:
                        new_sources.add(edge.provenance.system)
                    queue.append((next_id, path + [edge], new_sources))
        
        return paths
    
    def get_node_count(self) -> int:
        """Get total node count (excluding tombstones)."""
        return sum(1 for n in self._nodes.values() if not n.deleted_at)
    
    def get_edge_count(self) -> int:
        """Get total edge count (excluding tombstones)."""
        return sum(1 for e in self._edges.values() if not e.deleted_at)
    
    def get_tombstone_count(self) -> int:
        """Get count of tombstoned nodes and edges."""
        node_tombstones = sum(1 for n in self._nodes.values() if n.deleted_at)
        edge_tombstones = sum(1 for e in self._edges.values() if e.deleted_at)
        return node_tombstones + edge_tombstones
    
    def get_all_node_ids(self) -> set[str]:
        """Get all node IDs (for merge deletion detection)."""
        return set(self._nodes.keys())
    
    def get_all_edge_ids(self) -> set[str]:
        """Get all edge IDs (for merge deletion detection)."""
        return set(self._edges.keys())
    
    def get_edges_by_type(self, edge_type: str) -> List[Edge]:
        """Get all edges of a given type (immutable copies)."""
        edge_ids = self._edges_by_type.get(edge_type, [])
        return [copy.deepcopy(self._edges[eid]) for eid in edge_ids if self._edges[eid].deleted_at is None]
    
    def nodes(self) -> List[Node]:
        """Get all nodes (immutable copies, excluding tombstones)."""
        return [copy.deepcopy(node) for node in self._nodes.values() if not node.deleted_at]
    
    def edges(self) -> List[Edge]:
        """Get all edges (immutable copies, excluding tombstones)."""
        return [copy.deepcopy(edge) for edge in self._edges.values() if not edge.deleted_at]

