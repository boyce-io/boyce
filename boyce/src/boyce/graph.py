"""
Semantic Graph Construction - The Weaver

This module implements the deterministic graph construction system that turns
SemanticSnapshots into a traversable, mathematically weighted graph for pathfinding.

The graph uses networkx.MultiDiGraph to represent entities (nodes) and joins (edges),
with weights calculated based on semantic cost (explicit joins preferred, FK joins standard,
M:M avoided).

Join Weight Hierarchy:
- 0.1: Explicit dbt/LookML joins (Gold Standard — Preferred)
- 0.5: dbt source YAML joins (Silver Standard)
- 1.0: Foreign key joins (Standard)
- 2.0: Inferred edges (name-match heuristic — Bronze Standard)
- 100.0: Many-to-many (avoid)
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import networkx as nx

from .types import Entity, FieldDef, JoinDef, JoinType, SemanticSnapshot


class SemanticGraph:
    """
    Weighted directed graph for semantic pathfinding.

    Nodes = Entities (Tables/Views)
    Edges = Joins (with semantic weights)

    Weights:
    - 0.1: Explicit dbt/LookML joins (Gold Standard - Preferred)
    - 0.5: dbt source YAML joins (Silver Standard)
    - 1.0: Foreign Key joins (Standard)
    - 2.0: Inferred foreign key joins (Bronze Standard - High Cost)
    - 100.0: Many-to-Many relationships (Risky - Avoid)
    """

    def __init__(self) -> None:
        """Initialize an empty semantic graph."""
        self.graph = nx.MultiDiGraph()
        self.snapshots: Dict[str, SemanticSnapshot] = {}
        self.entity_to_snapshot: Dict[str, str] = {}  # entity_id -> snapshot_id
        self.field_cache: Dict[str, FieldDef] = {}  # field_id -> FieldDef (aggregated across snapshots)

    def add_snapshot(self, snapshot: SemanticSnapshot) -> None:
        """
        Add a SemanticSnapshot to the graph.

        Args:
            snapshot: SemanticSnapshot to add

        Logic:
            1. Add entities as nodes
            2. Add joins as edges with calculated weights
            3. Cache fields for SQL generation
        """
        self.snapshots[snapshot.snapshot_id] = snapshot

        for entity_id, entity in snapshot.entities.items():
            self.graph.add_node(entity_id, entity=entity, snapshot_id=snapshot.snapshot_id)
            self.entity_to_snapshot[entity_id] = snapshot.snapshot_id

        for field_id, field in snapshot.fields.items():
            self.field_cache[field_id] = field

        for join in snapshot.joins:
            weight = self._calculate_join_weight(join, snapshot)
            self.graph.add_edge(
                join.source_entity_id,
                join.target_entity_id,
                weight=weight,
                join=join,
                key=join.id,
            )

        self.infer_edges()

    def _calculate_join_weight(self, join: JoinDef, snapshot: SemanticSnapshot) -> float:
        """
        Calculate semantic weight for a join edge.

        Weight calculation:
        - 0.1: Gold Standard - Explicit joins from dbt manifest.json or LookML
        - 0.5: Silver Standard - Explicit joins from dbt source YAML files
        - 1.0: Foreign Key joins (source field is FOREIGN_KEY type)
        - 100.0: Many-to-Many (if description indicates M:M or both sides are not unique)
        - 1.0: Default (standard join)
        """
        source_type = snapshot.metadata.get("source_type", "")

        if join.description:
            desc_lower = join.description.lower()

            if source_type == "manifest" or "lookml join" in desc_lower:
                if "dbt relationship" in desc_lower or "lookml join" in desc_lower:
                    return 0.1

            if source_type == "source_yaml":
                if "dbt relationship" in desc_lower or "source yaml" in desc_lower:
                    return 0.5

        if source_type == "source_yaml":
            return 0.5

        source_field = snapshot.fields.get(join.source_field_id)
        if source_field and source_field.field_type.value == "FOREIGN_KEY":
            target_field = snapshot.fields.get(join.target_field_id)
            if target_field:
                if target_field.field_type.value == "FOREIGN_KEY" and not target_field.primary_key:
                    if join.description and (
                        "many_to_many" in join.description.lower() or "m:m" in join.description.lower()
                    ):
                        return 100.0
            return 1.0

        if join.description:
            desc_lower = join.description.lower()
            if "many_to_many" in desc_lower or "m:m" in desc_lower:
                return 100.0

        return 1.0

    def infer_edges(self) -> int:
        """
        Infer missing edges using the "Name Match" heuristic (Bronze Standard).

        Densifies the graph by inferring foreign key relationships where explicit
        metadata is missing. Uses dictionary lookups (O(1)) instead of nested loops.

        Logic:
        1. Build lookup dictionaries for fast entity/field matching
        2. Iterate through all Entities
        3. Look for columns ending in `_id` (e.g., `user_id`)
        4. Check if a corresponding Entity exists (e.g., `users` or `dim_users`)
           with a Primary Key (e.g., `id` or `user_id`)
        5. Create inferred edge with weight 2.0 (Bronze Standard)
        6. Skip if explicit edge already exists

        Returns:
            Number of inferred edges created
        """
        inferred_count = 0

        entity_name_lookup: Dict[str, Tuple[str, Dict[str, str]]] = {}

        for entity_id in self.graph.nodes():
            entity = self.graph.nodes[entity_id].get("entity")
            if not entity:
                continue

            pk_fields: Dict[str, str] = {}
            entity_fields = [
                self.field_cache[field_id]
                for field_id in entity.fields
                if field_id in self.field_cache
            ]

            for field in entity_fields:
                is_pk_or_id = (
                    field.primary_key
                    or field.field_type.value == "ID"
                    or field.name.endswith("_id")
                )
                if is_pk_or_id:
                    pk_fields[field.name] = field.id
                    if field.name == "id":
                        pk_fields["_default_id"] = field.id

            entity_name_lookup[entity.name] = (entity_id, pk_fields)

        for source_entity_id in self.graph.nodes():
            source_entity = self.graph.nodes[source_entity_id].get("entity")
            if not source_entity:
                continue

            source_fields = [
                self.field_cache[field_id]
                for field_id in source_entity.fields
                if field_id in self.field_cache
            ]

            for source_field in source_fields:
                if not source_field.name.endswith("_id"):
                    continue

                field_base = source_field.name[:-3]  # Remove "_id"

                potential_target_names = [
                    field_base,
                    field_base + "s",
                    "dim_" + field_base,
                    "dim_" + field_base + "s",
                    "fct_" + field_base,
                    "fct_" + field_base + "s",
                ]

                if field_base.startswith("stg_"):
                    potential_target_names.append(field_base[4:])
                    potential_target_names.append(field_base[4:] + "s")

                source_name = source_entity.name
                if source_name.startswith("stg_"):
                    potential_target_names.extend([
                        "dim_" + field_base,
                        "fct_" + field_base,
                        "dim_" + field_base + "s",
                        "fct_" + field_base + "s",
                    ])

                target_entity_id = None
                target_field_id = None

                for target_name in potential_target_names:
                    if target_name in entity_name_lookup:
                        candidate_entity_id, pk_fields = entity_name_lookup[target_name]

                        if source_field.name in pk_fields:
                            target_entity_id = candidate_entity_id
                            target_field_id = pk_fields[source_field.name]
                            break
                        elif "_default_id" in pk_fields:
                            target_entity_id = candidate_entity_id
                            target_field_id = pk_fields["_default_id"]
                            break
                        elif field_base in pk_fields:
                            target_entity_id = candidate_entity_id
                            target_field_id = pk_fields[field_base]
                            break

                        if target_entity_id:
                            break

                if target_entity_id and target_field_id:
                    edge_exists = False
                    if source_entity_id in self.graph:
                        if target_entity_id in self.graph[source_entity_id]:
                            for edge_key, edge_data in self.graph[source_entity_id][target_entity_id].items():
                                existing_join = edge_data.get("join")
                                if existing_join and not existing_join.id.startswith("inferred:"):
                                    edge_exists = True
                                    break

                    if edge_exists:
                        continue

                    inferred_join = JoinDef(
                        id=f"inferred:{source_entity.name}:{source_field.name}:{target_entity_id.replace('entity:', '')}",
                        source_entity_id=source_entity_id,
                        target_entity_id=target_entity_id,
                        join_type=JoinType.LEFT,
                        source_field_id=source_field.id,
                        target_field_id=target_field_id,
                        description=(
                            f"Inferred foreign key (Bronze Standard): "
                            f"{source_entity.name}.{source_field.name} -> "
                            f"{target_entity_id.replace('entity:', '')}"
                        ),
                    )

                    self.graph.add_edge(
                        source_entity_id,
                        target_entity_id,
                        weight=2.0,
                        join=inferred_join,
                        key=inferred_join.id,
                    )

                    inferred_count += 1

        return inferred_count

    def find_path(self, source_entity: str, target_entity: str) -> List[JoinDef]:
        """
        Find the shortest path between two entities using Dijkstra's algorithm.

        Args:
            source_entity: Entity ID of source entity
            target_entity: Entity ID of target entity

        Returns:
            List of JoinDef objects representing the path (empty if no path exists)

        Raises:
            ValueError: If source or target entity doesn't exist in graph
        """
        if source_entity not in self.graph:
            raise ValueError(f"Source entity not found: {source_entity}")
        if target_entity not in self.graph:
            raise ValueError(f"Target entity not found: {target_entity}")

        if source_entity == target_entity:
            return []

        try:
            path_nodes = nx.shortest_path(
                self.graph,
                source_entity,
                target_entity,
                weight="weight",
                method="dijkstra",
            )

            join_path: List[JoinDef] = []
            for i in range(len(path_nodes) - 1):
                source = path_nodes[i]
                target = path_nodes[i + 1]

                edges = self.graph[source][target]
                best_edge = None
                best_weight = float("inf")

                for edge_key, edge_data in edges.items():
                    edge_weight = edge_data.get("weight", 1.0)
                    if edge_weight < best_weight:
                        best_weight = edge_weight
                        best_edge = edge_data.get("join")

                if best_edge:
                    join_path.append(best_edge)

            return join_path

        except nx.NetworkXNoPath:
            return []

    def generate_join_sql(self, path: List[JoinDef], source_entity_id: str) -> str:
        """
        Generate SQL JOIN clauses from a path of joins.

        Args:
            path: List of JoinDef objects representing the join path
            source_entity_id: Entity ID to use as the base table (FROM clause)

        Returns:
            SQL string with FROM and JOIN clauses

        Example:
            FROM orders
            LEFT JOIN users ON orders.user_id = users.id
            LEFT JOIN products ON order_items.product_id = products.id
        """
        if not path:
            source_entity = self.graph.nodes[source_entity_id].get("entity")
            entity_name = source_entity.name if source_entity else source_entity_id.replace("entity:", "")
            return f"FROM {entity_name}"

        source_entity = self.graph.nodes[source_entity_id].get("entity")
        entity_name = source_entity.name if source_entity else source_entity_id.replace("entity:", "")
        sql_parts = [f"FROM {entity_name}"]

        for join in path:
            target_entity = self.graph.nodes[join.target_entity_id].get("entity")
            target_entity_name = (
                target_entity.name if target_entity else join.target_entity_id.replace("entity:", "")
            )

            source_field = self.field_cache.get(join.source_field_id)
            target_field = self.field_cache.get(join.target_field_id)

            source_field_name = source_field.name if source_field else join.source_field_id.split(":")[-1]
            target_field_name = target_field.name if target_field else join.target_field_id.split(":")[-1]

            source_entity_for_join = self.graph.nodes[join.source_entity_id].get("entity")
            source_entity_name = (
                source_entity_for_join.name
                if source_entity_for_join
                else join.source_entity_id.replace("entity:", "")
            )

            join_type_sql = {
                JoinType.INNER: "INNER JOIN",
                JoinType.LEFT: "LEFT JOIN",
                JoinType.RIGHT: "RIGHT JOIN",
                JoinType.FULL: "FULL OUTER JOIN",
            }.get(join.join_type, "LEFT JOIN")

            join_clause = (
                f"{join_type_sql} {target_entity_name} "
                f"ON {source_entity_name}.{source_field_name} = {target_entity_name}.{target_field_name}"
            )
            sql_parts.append(join_clause)

        return "\n".join(sql_parts)

    def get_entity_info(self, entity_id: str) -> Optional[Dict]:
        """
        Get information about an entity in the graph.

        Args:
            entity_id: Entity ID to query

        Returns:
            Dictionary with entity info, or None if not found
        """
        if entity_id not in self.graph:
            return None

        node_data = self.graph.nodes[entity_id]
        entity = node_data.get("entity")

        if not entity:
            return None

        return {
            "entity_id": entity_id,
            "name": entity.name,
            "schema": entity.schema_name,
            "grain": entity.grain,
            "field_count": len(entity.fields),
            "snapshot_id": node_data.get("snapshot_id"),
        }

    def list_entities(self) -> List[str]:
        """
        List all entity IDs in the graph.

        Returns:
            List of entity IDs
        """
        return list(self.graph.nodes())

    def get_entity_connections(self, entity_id: str) -> Dict[str, List[JoinDef]]:
        """
        Get all connections (joins) for an entity.

        Args:
            entity_id: Entity ID to query

        Returns:
            Dictionary with 'outgoing' and 'incoming' join lists
        """
        if entity_id not in self.graph:
            return {"outgoing": [], "incoming": []}

        outgoing: List[JoinDef] = []
        incoming: List[JoinDef] = []

        for target, edges in self.graph[entity_id].items():
            for edge_key, edge_data in edges.items():
                join = edge_data.get("join")
                if join:
                    outgoing.append(join)

        for source in self.graph.predecessors(entity_id):
            for edge_key in self.graph[source][entity_id]:
                edge_data = self.graph[source][entity_id][edge_key]
                join = edge_data.get("join")
                if join:
                    incoming.append(join)

        return {"outgoing": outgoing, "incoming": incoming}
