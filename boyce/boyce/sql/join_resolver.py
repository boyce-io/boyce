"""
Join Path Resolver - Deterministic JOIN clause generation from SemanticSnapshot.

This module implements the Join-Path Resolver that consumes JoinDef objects
from SemanticSnapshot to generate deterministic SQL JOIN clauses.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from boyce.types import JoinDef, JoinType, SemanticSnapshot
from boyce.sql.dialects import SQLDialect


class JoinPathResolver:
    """
    Resolves join paths from SemanticSnapshot JoinDef objects to SQL JOIN clauses.

    Contract:
        - Consumes JoinDef objects from SemanticSnapshot.joins
        - Ensures deterministic sequencing (sorted by entity_id for stability)
        - Defaults to LEFT OUTER JOIN unless JoinDef specifies INNER
        - Produces byte-stable SQL strings (same snapshot → same SQL)
    """

    def __init__(self, snapshot: SemanticSnapshot, dialect: SQLDialect):
        """
        Initialize join path resolver with snapshot and dialect.

        Args:
            snapshot: SemanticSnapshot containing JoinDef objects
            dialect: SQLDialect for identifier quoting
        """
        self.snapshot = snapshot
        self.dialect = dialect

    def resolve_join_path(
        self,
        source_entity_id: str,
        target_entity_ids: Optional[List[str]] = None
    ) -> Tuple[str, List[str]]:
        """
        Resolve join path from source entity to target entities.

        Args:
            source_entity_id: Starting entity ID (e.g., "entity:orders")
            target_entity_ids: Optional list of target entity IDs. If None, uses all
                             entities reachable from source via joins.

        Returns:
            Tuple of (from_clause, join_clauses):
            - from_clause: "FROM <source_table>"
            - join_clauses: List of "JOIN <table> ON <condition>" strings
        """
        # Get source entity name
        source_entity = self.snapshot.entities.get(source_entity_id)
        if not source_entity:
            raise ValueError(f"Source entity not found in snapshot: {source_entity_id}")

        source_name = source_entity.name
        source_quoted = self.dialect.quote_identifier(source_name)
        from_clause = f"FROM {source_quoted}"

        # If no target entities specified, find all reachable entities
        if target_entity_ids is None:
            target_entity_ids = self._find_reachable_entities(source_entity_id)

        # Build join clauses for each target entity
        join_clauses: List[str] = []
        visited_entities = {source_entity_id}

        # Use BFS to find join paths to each target
        for target_entity_id in target_entity_ids:
            if target_entity_id in visited_entities:
                continue

            # Find join path from source to target
            join_path = self.snapshot.find_join_path(source_entity_id, target_entity_id)

            if not join_path:
                # Try to find direct join
                direct_joins = self.snapshot.get_entity_joins(source_entity_id)
                for join_def in direct_joins:
                    if join_def.target_entity_id == target_entity_id:
                        join_path = [join_def]
                        break

            # Render each join in the path
            for join_def in join_path:
                if join_def.target_entity_id in visited_entities:
                    continue

                join_clause = self._render_join_def(join_def, visited_entities)
                if join_clause:
                    join_clauses.append(join_clause)
                    visited_entities.add(join_def.target_entity_id)

        return (from_clause, join_clauses)

    def resolve_joins_from_entity_list(
        self,
        entity_ids: List[str]
    ) -> Tuple[str, List[str]]:
        """
        Resolve joins for a list of entities, using the first as the FROM table.

        This method builds a sequential join chain: entity[0] → entity[1] → entity[2] → ...
        It uses find_join_path to discover multi-hop paths between consecutive entities.

        Args:
            entity_ids: List of entity IDs, first one is the FROM table

        Returns:
            Tuple of (from_clause, join_clauses)
        """
        if not entity_ids:
            raise ValueError("entity_ids cannot be empty")

        source_entity_id = entity_ids[0]
        source_entity = self.snapshot.entities.get(source_entity_id)
        if not source_entity:
            raise ValueError(f"Source entity not found: {source_entity_id}")

        source_name = source_entity.name
        source_quoted = self.dialect.quote_identifier(source_name)
        from_clause = f"FROM {source_quoted}"

        if len(entity_ids) == 1:
            return (from_clause, [])

        # Build sequential join chain
        join_clauses: List[str] = []
        visited_entities = {source_entity_id}

        # For each consecutive pair, find the join path
        for i in range(len(entity_ids) - 1):
            current_entity_id = entity_ids[i]
            next_entity_id = entity_ids[i + 1]

            # Find join path from current to next
            join_path = self.snapshot.find_join_path(current_entity_id, next_entity_id)

            if not join_path:
                # Try direct join
                direct_joins = self.snapshot.get_entity_joins(current_entity_id)
                for join_def in direct_joins:
                    if join_def.target_entity_id == next_entity_id:
                        join_path = [join_def]
                        break

            if not join_path:
                raise ValueError(
                    f"No join path found from {current_entity_id} to {next_entity_id}"
                )

            # Render each join in the path (skip if target already visited)
            for join_def in join_path:
                if join_def.target_entity_id in visited_entities:
                    continue

                join_clause = self._render_join_def(join_def, visited_entities)
                if join_clause:
                    join_clauses.append(join_clause)
                    visited_entities.add(join_def.target_entity_id)

        return (from_clause, join_clauses)

    def _find_reachable_entities(self, source_entity_id: str) -> List[str]:
        """
        Find all entities reachable from source via joins.

        Uses BFS to traverse the join graph.
        """
        reachable = []
        queue = [source_entity_id]
        visited = {source_entity_id}

        while queue:
            current = queue.pop(0)
            joins = self.snapshot.get_entity_joins(current)

            for join_def in joins:
                target = join_def.target_entity_id
                if target not in visited:
                    visited.add(target)
                    reachable.append(target)
                    queue.append(target)

        # Sort for determinism
        return sorted(reachable)

    def _render_join_def(
        self,
        join_def: JoinDef,
        visited_entities: set
    ) -> Optional[str]:
        """
        Render a single JoinDef into a SQL JOIN clause.

        Args:
            join_def: JoinDef to render
            visited_entities: Set of already-joined entity IDs (to avoid duplicates)

        Returns:
            SQL JOIN clause string, or None if entity already visited
        """
        # Skip if target already visited
        if join_def.target_entity_id in visited_entities:
            return None

        # Get entity names
        source_entity = self.snapshot.entities.get(join_def.source_entity_id)
        target_entity = self.snapshot.entities.get(join_def.target_entity_id)

        if not source_entity or not target_entity:
            return None

        # Get field names from field_ids
        source_field = self.snapshot.fields.get(join_def.source_field_id)
        target_field = self.snapshot.fields.get(join_def.target_field_id)

        if not source_field or not target_field:
            return None

        # Quote identifiers
        source_table_quoted = self.dialect.quote_identifier(source_entity.name)
        target_table_quoted = self.dialect.quote_identifier(target_entity.name)
        source_field_quoted = self.dialect.quote_identifier(source_field.name)
        target_field_quoted = self.dialect.quote_identifier(target_field.name)

        # Build join condition
        join_condition = f"{source_table_quoted}.{source_field_quoted} = {target_table_quoted}.{target_field_quoted}"

        # Determine join type (default to LEFT OUTER unless INNER)
        if join_def.join_type == JoinType.INNER:
            join_type_str = "INNER JOIN"
        elif join_def.join_type == JoinType.RIGHT:
            join_type_str = "RIGHT OUTER JOIN"
        elif join_def.join_type == JoinType.FULL:
            join_type_str = "FULL OUTER JOIN"
        else:
            # Default to LEFT OUTER JOIN
            join_type_str = "LEFT OUTER JOIN"

        return f"{join_type_str} {target_table_quoted} ON {join_condition}"
