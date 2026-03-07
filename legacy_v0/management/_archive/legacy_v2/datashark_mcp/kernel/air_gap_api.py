"""Air Gap API - The only interface allowed to the Planner.

This module provides the read-only API that untrusted components (like the Planner)
can use to access the ProjectedGraph. This is the ONLY interface that should be
exposed to untrusted components.
"""

import copy
from collections import deque
from typing import Any, Dict, List, Optional

from datashark_mcp.kernel.types import ProjectedGraph


class AirGapAPI:
    """Read-only API for accessing the ProjectedGraph.
    
    This is the ONLY interface that untrusted components should use to access
    graph data. It operates exclusively on the ProjectedGraph, never on the
    raw SemanticGraph.
    
    The AirGapAPI enforces the security boundary by ensuring that:
    1. Only projected (filtered) data is accessible
    2. No direct access to raw metadata is possible
    3. All operations are read-only
    """
    
    def __init__(self, projected_graph: ProjectedGraph):
        """Initialize with a ProjectedGraph (the only view untrusted components see).
        
        Args:
            projected_graph: The filtered graph view created by GraphProjector
        """
        self._projected_graph = projected_graph
    
    def get_schema_info(self, table_name: str) -> Optional[Dict]:
        """Get schema information for a table.
        
        This method searches the ProjectedGraph for the specified table.
        If the table was filtered out by policy, it will not be found.
        
        Args:
            table_name: Name of the table to query
        
        Returns:
            Dictionary containing schema information if table exists in projected graph,
            None if table is not found (either doesn't exist or was filtered by policy)
        """
        raw_data = self._projected_graph._raw_data
        
        # Search for the table in the projected graph
        if "entities" in raw_data and isinstance(raw_data["entities"], dict):
            if table_name in raw_data["entities"]:
                return raw_data["entities"][table_name]
        
        # Also check top-level keys (for simple structures)
        if table_name in raw_data:
            table_data = raw_data[table_name]
            if isinstance(table_data, dict):
                return table_data
        
        # Table not found in projected graph
        return None
    
    def search_concepts(self, search_term: str) -> List[str]:
        """Search for concepts matching a term.
        
        This method searches through the ProjectedGraph for concepts matching
        the search term. Only concepts that exist in the projected graph
        (i.e., passed policy filtering) will be found.
        
        Args:
            search_term: Term to search for (case-insensitive partial match)
        
        Returns:
            List of matching concept names found in projected graph
        """
        raw_data = self._projected_graph._raw_data
        matches = []
        
        # Search through all keys in the projected graph
        def search_recursive(data, path=""):
            """Recursively search through the data structure."""
            if isinstance(data, dict):
                for key, value in data.items():
                    current_path = f"{path}.{key}" if path else key
                    # Check if key matches search term (case-insensitive)
                    if search_term.lower() in key.lower():
                        matches.append(current_path)
                    # Recursively search nested structures
                    if isinstance(value, (dict, list)):
                        search_recursive(value, current_path)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, (dict, list)):
                        search_recursive(item, path)
        
        search_recursive(raw_data)
        return matches
    
    def get_all_entities(self) -> List[Dict]:
        """Get all entities from the projected graph.
        
        Returns a list of all entity dictionaries that exist in the projected graph.
        Only entities that passed policy filtering will be included.
        
        Returns:
            List of entity dictionaries. Each dictionary contains entity metadata
            (entity_id, entity_name, fields, etc.). Returns empty list if no entities
            are found or if entities structure is missing.
        """
        raw_data = self._projected_graph._raw_data
        
        # Try to get entities from the "entities" key (dictionary format)
        entities_dict = raw_data.get("entities", {})
        if isinstance(entities_dict, dict):
            # Convert dictionary to list of entity dictionaries
            entities = []
            for entity_id, entity_data in entities_dict.items():
                if isinstance(entity_data, dict):
                    # Create entity dict with entity_id and entity_data
                    entity = copy.deepcopy(entity_data)
                    # Ensure entity_id is included in the entity dict
                    if "entity_id" not in entity:
                        entity["entity_id"] = entity_id
                    # Ensure entity_name is included if missing
                    if "entity_name" not in entity:
                        entity["entity_name"] = entity_id
                    entities.append(entity)
            return entities
        
        # Try to get entities from a list format
        entities_list = raw_data.get("entities", [])
        if isinstance(entities_list, list):
            # Return deep copy of list
            return copy.deepcopy(entities_list)
        
        # No entities found
        return []
    
    def get_fields_by_entity(self, entity_id: str) -> List[Dict]:
        """Get all fields for a specific entity.
        
        Looks up the entity in the projected graph and returns its fields list.
        If the entity was filtered out by policy, it will not be found.
        
        Args:
            entity_id: Entity identifier to look up
        
        Returns:
            List of field dictionaries for the entity. Each dictionary contains
            field metadata (field_id, field_name, field_type, etc.). Returns
            empty list if entity not found or if fields are missing.
        """
        raw_data = self._projected_graph._raw_data
        
        # Try to get entity from "entities" dictionary
        entities_dict = raw_data.get("entities", {})
        if isinstance(entities_dict, dict):
            entity = entities_dict.get(entity_id)
            if isinstance(entity, dict):
                # Get fields from entity dict
                fields = entity.get("fields", [])
                if isinstance(fields, list):
                    return copy.deepcopy(fields)
                # If fields is a dict, convert to list
                if isinstance(fields, dict):
                    return [copy.deepcopy(fields)]
        
        # Try to get entity from top-level (if entities are stored as top-level keys)
        entity = raw_data.get(entity_id)
        if isinstance(entity, dict):
            fields = entity.get("fields", [])
            if isinstance(fields, list):
                return copy.deepcopy(fields)
            if isinstance(fields, dict):
                return [copy.deepcopy(fields)]
        
        # Try to get from "fields" key if entity_id matches a field structure
        # This handles cases where fields are stored separately
        fields_dict = raw_data.get("fields", {})
        if isinstance(fields_dict, dict):
            entity_fields = fields_dict.get(entity_id, [])
            if isinstance(entity_fields, list):
                return copy.deepcopy(entity_fields)
        
        # Entity not found or no fields
        return []
    
    def get_relationships_from(self, entity_id: str) -> List[Dict]:
        """Get all relationships where the source entity matches entity_id.
        
        Looks up relationships in the projected graph and filters by source_entity_id.
        Only relationships that passed policy filtering will be included.
        
        Args:
            entity_id: Source entity identifier to filter relationships
        
        Returns:
            List of relationship dictionaries where source_entity_id matches.
            Each dictionary contains relationship metadata (source_entity_id,
            target_entity_id, join_condition, confidence_score, etc.). Returns
            empty list if no relationships found or if relationships structure is missing.
        """
        raw_data = self._projected_graph._raw_data
        
        # Try to get relationships from "relationships" key
        relationships = raw_data.get("relationships", [])
        
        # Handle list format
        if isinstance(relationships, list):
            filtered = []
            for rel in relationships:
                if isinstance(rel, dict):
                    # Check if source_entity_id matches
                    source_id = rel.get("source_entity_id") or rel.get("source") or rel.get("from")
                    if source_id == entity_id:
                        filtered.append(copy.deepcopy(rel))
            return filtered
        
        # Handle dictionary format (keyed by source entity)
        if isinstance(relationships, dict):
            entity_rels = relationships.get(entity_id, [])
            if isinstance(entity_rels, list):
                return copy.deepcopy(entity_rels)
            if isinstance(entity_rels, dict):
                return [copy.deepcopy(entity_rels)]
        
        # Try to get from "edges" key (alternative naming)
        edges = raw_data.get("edges", [])
        if isinstance(edges, list):
            filtered = []
            for edge in edges:
                if isinstance(edge, dict):
                    source_id = edge.get("source_entity_id") or edge.get("source") or edge.get("from")
                    if source_id == entity_id:
                        filtered.append(copy.deepcopy(edge))
            return filtered
        
        # No relationships found
        return []
    
    def get_grain_by_entity(self, entity_id: str) -> Optional[str]:
        """Get the grain or primary key for a specific entity.
        
        Looks up the entity in the projected graph and returns its grain or
        primary_key field. If the entity was filtered out by policy, it will not be found.
        
        Args:
            entity_id: Entity identifier to look up
        
        Returns:
            Grain identifier string (e.g., "DAY", "CUSTOMER", "ORDER") or primary_key
            value if present. Returns None if entity not found or if grain/primary_key
            is missing.
        """
        raw_data = self._projected_graph._raw_data
        
        # Try to get entity from "entities" dictionary
        entities_dict = raw_data.get("entities", {})
        if isinstance(entities_dict, dict):
            entity = entities_dict.get(entity_id)
            if isinstance(entity, dict):
                # Try "grain" field first
                grain = entity.get("grain")
                if grain:
                    return str(grain)
                # Try "primary_key" field
                primary_key = entity.get("primary_key")
                if primary_key:
                    return str(primary_key)
                # Try "grain_id" field
                grain_id = entity.get("grain_id")
                if grain_id:
                    return str(grain_id)
        
        # Try to get entity from top-level
        entity = raw_data.get(entity_id)
        if isinstance(entity, dict):
            grain = entity.get("grain")
            if grain:
                return str(grain)
            primary_key = entity.get("primary_key")
            if primary_key:
                return str(primary_key)
            grain_id = entity.get("grain_id")
            if grain_id:
                return str(grain_id)
        
        # Try to get from "grains" key (if grains are stored separately)
        grains_dict = raw_data.get("grains", {})
        if isinstance(grains_dict, dict):
            grain = grains_dict.get(entity_id)
            if grain:
                return str(grain)
        
        # Entity not found or no grain/primary_key
        return None
    
    def find_entity(self, name: str) -> Optional[Dict[str, Any]]:
        """Find entity by name (case-insensitive exact match).
        
        Searches the projected graph for an entity matching the given name.
        Only entities that passed policy filtering will be found.
        
        Args:
            name: Entity name to search for (case-insensitive)
        
        Returns:
            Entity dictionary if found, None otherwise
        """
        target = name.lower()
        raw_data = self._projected_graph._raw_data
        
        # Try to get entities from "entities" dictionary
        entities_dict = raw_data.get("entities", {})
        if isinstance(entities_dict, dict):
            # Search by key (entity_id or entity_name)
            for entity_id, entity_data in entities_dict.items():
                if isinstance(entity_data, dict):
                    # Check entity_name field
                    entity_name = entity_data.get("entity_name", "").lower()
                    if entity_name == target:
                        return copy.deepcopy(entity_data)
                    # Also check if the key itself matches
                    if entity_id.lower() == target:
                        return copy.deepcopy(entity_data)
        
        # Try to get entities from list format
        entities_list = raw_data.get("entities", [])
        if isinstance(entities_list, list):
            for ent in entities_list:
                if isinstance(ent, dict):
                    entity_name = ent.get("name", "").lower() or ent.get("entity_name", "").lower()
                    if entity_name == target:
                        return copy.deepcopy(ent)
                    # Check entity_id
                    entity_id = ent.get("entity_id", "").lower()
                    if entity_id == target:
                        return copy.deepcopy(ent)
        
        # Try top-level key match
        entity = raw_data.get(name)
        if isinstance(entity, dict):
            return copy.deepcopy(entity)
        
        # Entity not found
        return None
    
    def resolve_entity(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Resolve entity reference to full metadata (alias for find_entity).
        
        This method provides compatibility with ContextAPI.resolve_entity().
        It performs the same lookup as find_entity() but may be extended
        in the future to handle additional resolution logic (aliases, etc.).
        
        Args:
            identifier: Entity identifier (name, ID, or alias)
        
        Returns:
            Entity metadata dictionary if found, None otherwise
        """
        return self.find_entity(identifier)
    
    def get_salience(self, entity_id: str) -> float:
        """Get salience score for an entity (stub implementation).
        
        This is a placeholder that returns 1.0 for all entities in the
        projected graph. In a full implementation, this would return
        actual salience scores from the semantic graph.
        
        Args:
            entity_id: Entity identifier
        
        Returns:
            Salience score (currently always 1.0 for entities in projection)
        """
        # Check if entity exists in projected graph
        entity = self.find_entity(entity_id)
        if entity:
            return 1.0
        return 0.0
    
    def validate_query_plan(self, plan: Dict[str, Any]) -> bool:
        """Validate that all tables in the plan exist in the projected graph.
        
        Verifies that all tables referenced in the query plan are accessible
        in the projected graph (i.e., passed policy filtering).
        
        Args:
            plan: Query plan dictionary containing "tables" key with list of table names
        
        Returns:
            True if all tables are valid (exist in projected graph), False otherwise
        """
        raw_data = self._projected_graph._raw_data
        
        # Get all valid entity names from projected graph
        valid_tables = set()
        
        # Try to get entities from dictionary format
        entities_dict = raw_data.get("entities", {})
        if isinstance(entities_dict, dict):
            for entity_id, entity_data in entities_dict.items():
                if isinstance(entity_data, dict):
                    # Add entity_name if present
                    entity_name = entity_data.get("entity_name") or entity_data.get("name")
                    if entity_name:
                        valid_tables.add(entity_name)
                    # Also add entity_id as valid
                    valid_tables.add(entity_id)
        
        # Try to get entities from list format
        entities_list = raw_data.get("entities", [])
        if isinstance(entities_list, list):
            for ent in entities_list:
                if isinstance(ent, dict):
                    entity_name = ent.get("entity_name") or ent.get("name")
                    if entity_name:
                        valid_tables.add(entity_name)
                    entity_id = ent.get("entity_id")
                    if entity_id:
                        valid_tables.add(entity_id)
        
        # Get plan tables
        plan_tables = plan.get("tables", [])
        if not plan_tables:
            # Empty plan is considered valid
            return True
        
        # Check if all plan tables exist in valid_tables
        return all(t in valid_tables for t in plan_tables)
    
    def find_join_path(self, start_table: str, end_table: str) -> Optional[Dict[str, Any]]:
        """Find shortest join path between two tables using BFS.
        
        Implements breadth-first search over relationships in the projected graph
        to find the shortest path between two tables. Only relationships that
        passed policy filtering will be considered.
        
        This method returns a dictionary compatible with ContextAPI.find_join_path()
        which is used by the reasoning module's join planner.
        
        Args:
            start_table: Source table identifier
            end_table: Target table identifier
        
        Returns:
            Path dictionary with structure:
            {
                "path": [relationship1, relationship2, ...],
                "depth": int,
                "path_score": float (optional),
                "sources_involved": [table1, table2, ...] (optional)
            }
            Returns None if no path exists. Returns {"path": [], "depth": 0} if start == end.
        """
        # Handle edge case: same table
        if start_table == end_table:
            return {"path": [], "depth": 0, "path_score": 1.0, "sources_involved": []}
        
        raw_data = self._projected_graph._raw_data
        
        # Step 1: Build adjacency map from relationships
        relationships = raw_data.get("relationships", [])
        adj: Dict[str, List[Dict[str, Any]]] = {}
        
        # Handle list format
        if isinstance(relationships, list):
            for rel in relationships:
                if isinstance(rel, dict):
                    # Extract source and target
                    source = rel.get("source_entity_id") or rel.get("source") or rel.get("from")
                    target = rel.get("target_entity_id") or rel.get("target") or rel.get("to")
                    
                    if source and target:
                        # Add edge from source to target
                        if source not in adj:
                            adj[source] = []
                        adj[source].append(copy.deepcopy(rel))
                        
                        # Also add reverse edge for bidirectional traversal
                        # (relationships can typically be traversed in both directions)
                        if target not in adj:
                            adj[target] = []
                        # Create reverse relationship
                        reverse_rel = copy.deepcopy(rel)
                        reverse_rel["source_entity_id"] = target
                        reverse_rel["target_entity_id"] = source
                        adj[target].append(reverse_rel)
        
        # Handle dictionary format (keyed by source)
        elif isinstance(relationships, dict):
            for source, rels in relationships.items():
                if isinstance(rels, list):
                    adj[source] = [copy.deepcopy(r) for r in rels if isinstance(r, dict)]
                elif isinstance(rels, dict):
                    adj[source] = [copy.deepcopy(rels)]
        
        # Step 2: Perform BFS from start_table to end_table
        if start_table not in adj:
            # Start table has no relationships
            return None
        
        # BFS queue: (current_table, path_so_far, depth, sources_visited)
        queue = deque([(start_table, [], 0, {start_table})])
        visited = {start_table}
        
        while queue:
            current_table, path_so_far, depth, sources_visited = queue.popleft()
            
            # Check if we've reached the target
            if current_table == end_table:
                # Reconstruct path from relationships
                path_edges = []
                for rel in path_so_far:
                    path_edges.append(rel)
                
                return {
                    "path": path_edges,
                    "depth": depth,
                    "path_score": 1.0 / (depth + 1) if depth > 0 else 1.0,  # Higher depth = lower score
                    "sources_involved": list(sources_visited)
                }
            
            # Explore neighbors
            neighbors = adj.get(current_table, [])
            for rel in neighbors:
                target = rel.get("target_entity_id") or rel.get("target") or rel.get("to")
                if target and target not in visited:
                    visited.add(target)
                    # Add relationship to path
                    new_path = path_so_far + [rel]
                    new_sources = sources_visited | {target}
                    queue.append((target, new_path, depth + 1, new_sources))
        
        # No path found
        return None

