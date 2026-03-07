"""
Public Context API

Read-only facade over the unified semantic graph.
Returns immutable views (deep copies) and logs metrics.
"""

from __future__ import annotations

import copy
import logging
import time
from typing import Any, Dict, List, Optional, Deque, Set, Tuple
from collections import deque
from datashark_mcp.context.models import Node, Edge
from datashark_mcp.context.store import GraphStore


logger = logging.getLogger(__name__)


class ContextAPI:
    """
    Read-only facade over the unified semantic graph.
    
    Methods return deep-copied immutable views to prevent external mutation.
    All operations log metrics for telemetry.
    """
    
    def __init__(self, store: GraphStore) -> None:
        """
        Initialize Context API.
        
        Args:
            store: GraphStore instance
        """
        self._store = store
        self._run_id: Optional[str] = None
    
    def set_run_id(self, run_id: str) -> None:
        """Set run_id for telemetry correlation."""
        self._run_id = run_id
    
    def _log_metric(
        self,
        phase: str,
        api_method: str,
        duration_ms: float,
        node_count: Optional[int] = None,
        edge_count: Optional[int] = None
    ) -> None:
        """Log telemetry metric."""
        log_data = {
            "run_id": self._run_id,
            "phase": phase,
            "api_method": api_method,
            "duration_ms": duration_ms,
        }
        if node_count is not None:
            log_data["node_count"] = node_count
        if edge_count is not None:
            log_data["edge_count"] = edge_count
        
        logger.info(f"ContextAPI metric: {log_data}")
    
    def find_entity(self, name: str, system: Optional[str] = None) -> Optional[Node]:
        """
        Find entity by name, optionally filtered by system.
        
        Args:
            name: Entity name (e.g., "public.meta", "fact_orders")
            system: Optional system filter
        
        Returns:
            Node if found, None otherwise
        
        Performance: <1ms (indexed lookup)
        """
        start = time.time()
        try:
            # Search by name first
            results = self._store.search(name, filters={"system": [system]} if system else None)
            # Filter to exact name match and type=ENTITY
            for node in results:
                if node.name == name and node.type == "ENTITY":
                    result = copy.deepcopy(node)
                    duration = (time.time() - start) * 1000
                    self._log_metric("query", "find_entity", duration)
                    return result
            return None
        finally:
            duration = (time.time() - start) * 1000
            self._log_metric("query", "find_entity", duration)
    
    def find_entities_by_system(self, system: str) -> List[Node]:
        """
        Get all entities for a given system.
        
        Args:
            system: System identifier (e.g., "database", "dbt", "airflow")
        
        Returns:
            List of nodes (deep copies)
        
        Performance: <10ms (filtered search)
        """
        start = time.time()
        try:
            nodes = self._store.find_entities_by_system(system)
            result = [copy.deepcopy(node) for node in nodes]
            duration = (time.time() - start) * 1000
            self._log_metric("query", "find_entities_by_system", duration, node_count=len(result))
            return result
        finally:
            duration = (time.time() - start) * 1000
            self._log_metric("query", "find_entities_by_system", duration)
    
    def find_entities_by_repo(self, repo: str) -> List[Node]:
        """
        Get all entities for a given repository.
        
        Args:
            repo: Repository identifier
        
        Returns:
            List of nodes (deep copies)
        
        Performance: <10ms (filtered search)
        """
        start = time.time()
        try:
            nodes = self._store.find_entities_by_repo(repo)
            result = [copy.deepcopy(node) for node in nodes]
            duration = (time.time() - start) * 1000
            self._log_metric("query", "find_entities_by_repo", duration, node_count=len(result))
            return result
        finally:
            duration = (time.time() - start) * 1000
            self._log_metric("query", "find_entities_by_repo", duration)
    
    def search(self, term: str, filters: Optional[Dict[str, List[str]]] = None) -> List[Node]:
        """
        Search entities by term with optional filters.
        
        Args:
            term: Search term
            filters: Optional filters (e.g., {"system": ["database"], "type": ["ENTITY"]})
        
        Returns:
            List of matching nodes (deep copies)
        
        Performance: <10ms (indexed search)
        """
        start = time.time()
        try:
            nodes = self._store.search(term, filters=filters)
            result = [copy.deepcopy(node) for node in nodes]
            duration = (time.time() - start) * 1000
            self._log_metric("query", "search", duration, node_count=len(result))
            return result
        finally:
            duration = (time.time() - start) * 1000
            self._log_metric("query", "search", duration)
    
    def find_join_paths_from(self, node_id: str, max_depth: int = 5) -> List[Dict[str, Any]]:
        """
        Find all join paths from a node.
        
        Args:
            node_id: Source node ID
            max_depth: Maximum path depth
        
        Returns:
            List of path dictionaries with structure:
            {
                "path": [edge1, edge2, ...],
                "depth": int,
                "target": node_id
            }
        
        Performance: ≤100ms p95 (BFS with frontier pruning)
        """
        start = time.time()
        try:
            paths = self._store.find_join_paths_from(node_id, max_depth=max_depth)
            result = [
                {
                    "path": [copy.deepcopy(edge) for edge in path],
                    "depth": len(path),
                    "target": path[-1].dst if path else node_id
                }
                for path in paths
            ]
            duration = (time.time() - start) * 1000
            self._log_metric("query", "find_join_paths_from", duration, edge_count=sum(len(p["path"]) for p in result))
            return result
        finally:
            duration = (time.time() - start) * 1000
            self._log_metric("query", "find_join_paths_from", duration)
    
    def find_join_path(self, src_id: str, dst_id: str) -> Optional[Dict[str, Any]]:
        """
        Find shortest join path between two nodes.
        
        Args:
            src_id: Source node ID
            dst_id: Destination node ID
        
        Returns:
            Path dictionary or None if no path exists
            {
                "path": [edge1, edge2, ...],
                "depth": int
            }
        
        Performance: ≤100ms p95 (BFS)
        """
        start = time.time()
        try:
            # Get all paths from source
            paths = self._store.find_join_paths_from(src_id, max_depth=10)
            
            # Find path to destination
            for path in paths:
                if path and path[-1].dst == dst_id:
                    result = {
                        "path": [copy.deepcopy(edge) for edge in path],
                        "depth": len(path)
                    }
                    duration = (time.time() - start) * 1000
                    self._log_metric("query", "find_join_path", duration, edge_count=len(path))
                    return result
            
            return None
        finally:
            duration = (time.time() - start) * 1000
            self._log_metric("query", "find_join_path", duration)
    
    def resolve_entity(self, value: str) -> Optional[Dict[str, Any]]:
        """
        Resolve entity reference to full metadata.
        
        Args:
            value: Entity reference (name, ID, or alias)
        
        Returns:
            Entity metadata dict or None
        """
        start = time.time()
        try:
            # Try as ID first
            node = self._store.get_node(value)
            if node:
                result = copy.deepcopy(node).to_dict()
                duration = (time.time() - start) * 1000
                self._log_metric("query", "resolve_entity", duration)
                return result
            
            # Try as name
            node = self.find_entity(value)
            if node:
                result = copy.deepcopy(node).to_dict()
                duration = (time.time() - start) * 1000
                self._log_metric("query", "resolve_entity", duration)
                return result
            
            return None
        finally:
            duration = (time.time() - start) * 1000
            self._log_metric("query", "resolve_entity", duration)
    
    def get_schema_tree(self, system: str = "database") -> Dict[str, Any]:
        """
        Get hierarchical schema tree: System → Schema → Table → Column.
        
        Args:
            system: System identifier (default: "database")
        
        Returns:
            Nested dictionary structure:
            {
                "system": "database",
                "schemas": {
                    "schema_name": {
                        "name": "schema_name",
                        "tables": {
                            "table_name": {
                                "name": "table_name",
                                "columns": [
                                    {"name": "col1", "type": "varchar", ...},
                                    ...
                                ]
                            }
                        }
                    }
                }
            }
        
        Performance: <2s for full tree (cached)
        """
        start = time.time()
        try:
            # Get all entities for system
            entities = self.find_entities_by_system(system)
            
            # Build tree structure
            tree = {
                "system": system,
                "schemas": {}
            }
            
            # Group by schema
            for entity in entities:
                if entity.type != "ENTITY":
                    continue
                
                schema_name = entity.schema or "default"
                table_name = entity.name
                
                # Initialize schema if needed
                if schema_name not in tree["schemas"]:
                    tree["schemas"][schema_name] = {
                        "name": schema_name,
                        "tables": {}
                    }
                
                # Initialize table if needed
                if table_name not in tree["schemas"][schema_name]["tables"]:
                    tree["schemas"][schema_name]["tables"][table_name] = {
                        "name": table_name,
                        "columns": []
                    }
                
                # Get columns (FIELD nodes connected to this ENTITY)
                # Find edges where this entity is the source
                all_edges = self._store.get_edges_by_type("DESCRIBES")
                for edge in all_edges:
                    if edge.src == entity.id:
                        # Get the field node
                        field_node = self._store.get_node(edge.dst)
                        if field_node and field_node.type == "FIELD":
                            col_info = {
                                "name": field_node.name,
                                "type": field_node.attributes.get("data_type", "unknown"),
                                "nullable": field_node.attributes.get("nullable", True),
                                "default": field_node.attributes.get("default")
                            }
                            tree["schemas"][schema_name]["tables"][table_name]["columns"].append(col_info)
            
            # Convert nested dicts to lists for JSON serialization
            result = {
                "system": system,
                "schemas": [
                    {
                        "name": schema_name,
                        "tables": [
                            {
                                "name": table_name,
                                "columns": table_data["columns"]
                            }
                            for table_name, table_data in schema_data["tables"].items()
                        ]
                    }
                    for schema_name, schema_data in sorted(tree["schemas"].items())
                ]
            }
            
            duration = (time.time() - start) * 1000
            self._log_metric("query", "get_schema_tree", duration, node_count=len(entities))
            return result
        finally:
            duration = (time.time() - start) * 1000
            self._log_metric("query", "get_schema_tree", duration)
