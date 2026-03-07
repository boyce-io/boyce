"""
Join Planner implementation for Advanced Join Reasoning (Principle 4).

Implements multi-hop join path inference using confidence-weighted graph search.
This component leverages RELATIONSHIP definitions from the SNAPSHOT_SCHEMA_CONTRACT
to find optimal join paths between entities.
"""

from __future__ import annotations

import heapq
from typing import Any, Dict, List, Optional, Tuple

from datashark_mcp.kernel.air_gap_api import AirGapAPI


class JoinPlanner:
    """
    Join path inference engine using confidence-weighted graph search.
    
    Contract:
        - Finds optimal join paths between entities using RELATIONSHIP edges
        - Uses confidence_score from RELATIONSHIP edges for path ranking
        - Implements Principle 4 (Confidence-Aware Reasoning)
        - Returns deterministic paths (same inputs → same outputs)
        - Uses AirGapAPI interface for graph access (read-only, projected graph only)
    """
    
    def __init__(self, air_gap_api: AirGapAPI) -> None:
        """
        Initialize join planner with AirGapAPI.
        
        Args:
            air_gap_api: AirGapAPI instance providing read-only access to the
                ProjectedGraph. This ensures the Safety Kernel boundary is maintained.
        """
        self.api = air_gap_api
    
    def infer_join_path(
        self,
        start_entity_id: str,
        target_entity_id: str
    ) -> List[Tuple[str, str, str]]:
        """
        Infer optimal join path between two entities using confidence-weighted graph search.
        
        Implements Dijkstra's algorithm with confidence scores as edge weights.
        Path cost is calculated as the inverse of confidence_score (lower confidence = higher cost),
        so paths with higher confidence scores are preferred.
        
        Contract:
            - Performs graph search over RELATIONSHIP edges in SemanticGraph
            - Uses confidence_score inversely for path cost calculation
            - Returns optimal path (highest accumulated confidence)
            - Returns empty list if no path exists
            - Deterministic: same inputs → same outputs
        
        Args:
            start_entity_id: Canonical entity identifier for the source entity
            target_entity_id: Canonical entity identifier for the target entity
        
        Returns:
            List of tuples representing the optimal join path:
            - Each tuple is (source_entity_id, target_entity_id, join_condition_sql)
            - Path is ordered from start to target
            - Empty list [] if no path exists between entities
        
        Example:
            >>> planner = JoinPlanner(semantic_graph)
            >>> path = planner.infer_join_path("entity:channels", "entity:viewership_metrics")
            >>> path
            [("entity:channels", "entity:viewership_metrics", "channels.channel_id = viewership_metrics.channel_id")]
        
        Algorithm:
            Uses Dijkstra's algorithm with:
            - Edge weight = 1.0 - confidence_score  # Inverse: lower confidence = higher cost
            - Priority queue for efficient path exploration
            - Path reconstruction via predecessor tracking
        """
        # Handle edge case: same entity
        if start_entity_id == target_entity_id:
            return []
        
        # Dijkstra's algorithm with confidence-weighted edges
        # Priority queue: (accumulated_cost, current_entity_id, path_so_far)
        # Lower cost = higher priority (we want highest confidence = lowest cost)
        priority_queue: List[Tuple[float, str, List[Tuple[str, str, str]]]] = []
        heapq.heappush(priority_queue, (0.0, start_entity_id, []))
        
        # Track visited entities and their best costs
        visited: Dict[str, float] = {}
        # Track predecessors for path reconstruction: entity_id -> (prev_entity_id, relationship)
        predecessors: Dict[str, Tuple[str, Dict[str, Any]]] = {}
        
        while priority_queue:
            current_cost, current_entity_id, current_path = heapq.heappop(priority_queue)
            
            # Skip if we've already found a better path to this entity
            if current_entity_id in visited and visited[current_entity_id] < current_cost:
                continue
            
            # Mark as visited with this cost
            visited[current_entity_id] = current_cost
            
            # Check if we've reached the target
            if current_entity_id == target_entity_id:
                # Reconstruct path from predecessors
                return self._reconstruct_path(
                    start_entity_id,
                    target_entity_id,
                    predecessors
                )
            
            # Get all relationships from current entity
            try:
                relationships = self.api.get_relationships_from(current_entity_id)
            except KeyError:
                # Entity not found in graph, skip
                continue
            
            # Explore all outgoing relationships
            for relationship in relationships:
                target_entity = relationship.get("target_entity_id")
                if not target_entity:
                    continue
                
                # Skip if already visited (we've found optimal path to this entity)
                if target_entity in visited:
                    continue
                
                # Get confidence score (default to 0.5 if missing)
                confidence_score = relationship.get("confidence_score", 0.5)
                # Ensure confidence is in valid range [0.0, 1.0]
                confidence_score = max(0.0, min(1.0, float(confidence_score)))
                
                # Calculate edge cost: inverse of confidence (lower confidence = higher cost)
                # Use 1 - confidence to ensure higher confidence = lower cost
                # Add small epsilon to avoid zero cost for perfect confidence
                edge_cost = 1.0 - confidence_score + 1e-6
                
                # Calculate new path cost
                new_cost = current_cost + edge_cost
                
                # Get join condition SQL
                join_condition_sql = relationship.get("join_condition_sql", "")
                
                # Check if we've found a better path to this target entity
                if target_entity not in visited or new_cost < visited.get(target_entity, float('inf')):
                    # Update predecessor for path reconstruction
                    predecessors[target_entity] = (current_entity_id, relationship)
                    
                    # Add to priority queue
                    heapq.heappush(priority_queue, (new_cost, target_entity, []))
        
        # No path found
        return []
    
    def _reconstruct_path(
        self,
        start_entity_id: str,
        target_entity_id: str,
        predecessors: Dict[str, Tuple[str, Dict[str, Any]]]
    ) -> List[Tuple[str, str, str]]:
        """
        Reconstruct join path from predecessor map.
        
        Args:
            start_entity_id: Source entity identifier
            target_entity_id: Target entity identifier
            predecessors: Dictionary mapping entity_id -> (prev_entity_id, relationship_dict)
        
        Returns:
            List of tuples: [(source_entity_id, target_entity_id, join_condition_sql)]
            Ordered from start to target
        """
        path: List[Tuple[str, str, str]] = []
        current_entity = target_entity_id
        
        # Reconstruct path backwards from target to start
        while current_entity != start_entity_id:
            if current_entity not in predecessors:
                # Path reconstruction failed (should not happen in valid paths)
                return []
            
            prev_entity, relationship = predecessors[current_entity]
            join_condition_sql = relationship.get("join_condition_sql", "")
            
            # Prepend to path (we're building backwards)
            path.insert(0, (prev_entity, current_entity, join_condition_sql))
            
            current_entity = prev_entity
        
        return path

