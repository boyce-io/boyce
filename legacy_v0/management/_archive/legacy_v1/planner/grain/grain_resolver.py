"""
Grain Resolver implementation for determining optimal aggregation levels.

Implements grain resolution logic to find the Lowest Common Denominator (LCD) grain
for a set of required entities, ensuring correct aggregation of METRICS and preventing
fan-out/double-counting errors.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from datashark_mcp.kernel.air_gap_api import AirGapAPI


class GrainResolver:
    """
    Grain resolution engine for determining optimal aggregation levels.
    
    Contract:
        - Finds LCD grain for required entities using GRAIN definitions
        - Uses grain_level property to determine fineness hierarchy
        - Prevents fan-out/double-counting errors in metric aggregation
        - Returns grain_context conforming to PLANNER_IO_CONTRACT
        - Uses AirGapAPI interface for graph access (read-only, projected graph only)
    """
    
    # Predefined grain level hierarchy (finer = higher number)
    # This defines the relative fineness of different grain levels
    # Lower numbers = coarser grain, Higher numbers = finer grain
    GRAIN_LEVEL_HIERARCHY: Dict[str, int] = {
        # Time-based grains (coarser to finer)
        "YEARLY": 1,
        "QUARTERLY": 2,
        "MONTHLY": 3,
        "WEEKLY": 4,
        "DAY": 5,
        "HOURLY": 6,
        # Entity-based grains
        "CUSTOMER": 10,
        "USER": 11,
        "ORDER": 12,
        "ORDER_LINE": 13,
        "TRANSACTION": 14,
        "EVENT": 15,
        # Dimension-based grains
        "CHANNEL": 20,
        "PRODUCT": 21,
        "REGION": 22,
        # Base/default grain (coarsest)
        "BASE": 0,
    }
    
    def __init__(self, air_gap_api: AirGapAPI) -> None:
        """
        Initialize grain resolver with AirGapAPI.
        
        Args:
            air_gap_api: AirGapAPI instance providing read-only access to the
                ProjectedGraph. This ensures the Safety Kernel boundary is maintained.
        """
        self.api = air_gap_api
        # Cache for grain lookups: entity_id -> grain_dict
        self._grain_cache: Dict[str, Dict[str, Any]] = {}
    
    def resolve_final_grain(self, required_entity_ids: List[str]) -> Dict[str, Any]:
        """
        Resolve the optimal Lowest Common Denominator (LCD) grain for required entities.
        
        Determines the finest grain that satisfies all required entities, ensuring
        correct aggregation of METRICS and preventing fan-out/double-counting errors.
        
        Contract:
            - Finds LCD grain using GRAIN definitions from SNAPSHOT_SCHEMA_CONTRACT
            - Uses grain_level property to determine fineness hierarchy
            - Returns grain_context conforming to PLANNER_IO_CONTRACT
            - Returns default grain context if input is empty
            - Deterministic: same inputs → same outputs
        
        Args:
            required_entity_ids: List of entity_id strings that must be present in
                the final query. This includes base entities of all requested Metrics.
        
        Returns:
            Dictionary conforming to PLANNER_IO_CONTRACT grain_context schema:
            - grain_id (str): ID of the resolved LCD grain
            - grain_level (str): Grain level identifier (e.g., "DAY", "ORDER_LINE")
            - grouping_fields (list[str]): List of fields for GROUP BY clause
            - aggregation_required (bool): True if aggregation is needed
            - time_dimension (str, optional): Time dimension field name if grain is time-based
        
        Example:
            >>> resolver = GrainResolver(semantic_graph)
            >>> context = resolver.resolve_final_grain(["entity:orders", "entity:order_lines"])
            >>> context
            {
                "grain_id": "grain:order_line",
                "grain_level": "ORDER_LINE",
                "grouping_fields": ["order_id", "line_item_id"],
                "aggregation_required": False
            }
        """
        # Edge case: empty input returns default grain context
        if not required_entity_ids:
            return self._default_grain_context()
        
        # Get grains for all required entities
        entity_grains: List[Dict[str, Any]] = []
        for entity_id in required_entity_ids:
            grain = self._get_grain_for_entity(entity_id)
            if grain:
                entity_grains.append(grain)
        
        # If no grains found, return default
        if not entity_grains:
            return self._default_grain_context()
        
        # Find the finest grain (LCD) - highest hierarchy number = finest
        lcd_grain = self._find_finest_grain(entity_grains)
        
        # Determine if aggregation is needed
        # Aggregation is needed if any entity's grain is finer than the LCD
        aggregation_needed = any(
            self._is_grain_finer(grain, lcd_grain)
            for grain in entity_grains
            if grain != lcd_grain
        )
        
        # Get group_by_fields for the LCD grain
        group_by_fields = self._get_group_by_fields(lcd_grain)
        
        # Build grain_context conforming to PLANNER_IO_CONTRACT
        grain_context = {
            "grain_id": lcd_grain.get("grain_id", ""),
            "grain_level": lcd_grain.get("grain_level", "BASE"),
            "grouping_fields": group_by_fields,
            "aggregation_required": aggregation_needed,
        }
        
        # Add optional time_dimension if present
        time_dimension = lcd_grain.get("time_dimension")
        if time_dimension:
            grain_context["time_dimension"] = time_dimension
        
        return grain_context
    
    def _get_grain_for_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the GRAIN node associated with an entity.
        
        Looks up the entity's grain_id property and retrieves the corresponding
        GRAIN node from the semantic graph.
        
        Args:
            entity_id: Canonical entity identifier
        
        Returns:
            GRAIN dictionary conforming to SNAPSHOT_SCHEMA_CONTRACT, or None if
            entity has no grain or grain not found
        """
        # Check cache first
        if entity_id in self._grain_cache:
            return self._grain_cache[entity_id]
        
        try:
            # Get all entities and find the one matching entity_id
            entities = self.api.get_all_entities()
            entity = next((e for e in entities if e.get("entity_id") == entity_id), None)
            
            if not entity:
                return None
            
            # Get grain_id from entity (optional property)
            grain_id = entity.get("grain_id")
            if not grain_id:
                # Try to find grain by entity_id (grain.entity_id == entity_id)
                grain = self._find_grain_by_entity_id(entity_id)
                if grain:
                    self._grain_cache[entity_id] = grain
                    return grain
                return None
            
            # Get grain by grain_id using SemanticGraph interface
            try:
                # Note: get_grain_by_entity expects entity_id, not grain_id
                # For now, we'll need to look up grain differently
                # This is a placeholder - full implementation would require
                # additional AirGapAPI methods for grain lookup
                grain = None  # TODO: Implement grain lookup via AirGapAPI
                if grain:
                    self._grain_cache[entity_id] = grain
                return grain
            except KeyError:
                return None
            
        except (KeyError, AttributeError):
            return None
    
    def _find_grain_by_entity_id(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """
        Find a GRAIN node by its entity_id property.
        
        This method searches for grains where grain.entity_id matches the given
        entity_id. This requires access to all GRAIN nodes, which may need to be
        added to the SemanticGraph interface (e.g., get_all_grains() or get_grain_by_entity_id()).
        
        Implementation Note:
            This method currently returns None as a placeholder. The actual implementation
            will depend on the SemanticGraph's ability to query GRAIN nodes. Options include:
            1. Adding get_all_grains() to SemanticGraph and filtering here
            2. Adding get_grain_by_entity_id() to SemanticGraph
            3. Accessing grains through an internal graph structure
        
        Args:
            entity_id: Entity identifier to search for
        
        Returns:
            GRAIN dictionary conforming to SNAPSHOT_SCHEMA_CONTRACT, or None if not found
        """
        # TODO: Implement based on SemanticGraph API for accessing GRAIN nodes
        # For now, return None (will be handled by fallback to default grain)
        return None
    
    def _get_grain_by_id(self, grain_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a GRAIN node by its grain_id.
        
        This method retrieves grain details by grain_id using the SemanticGraph interface.
        This is a helper method that wraps the SemanticGraph.get_grain_by_id() call.
        
        Args:
            grain_id: Grain identifier
        
        Returns:
            GRAIN dictionary conforming to SNAPSHOT_SCHEMA_CONTRACT, or None if not found
        """
        try:
            # Note: AirGapAPI doesn't have get_grain_by_id, only get_grain_by_entity
            # This is a placeholder - full implementation would require
            # additional AirGapAPI methods for grain lookup by ID
            return None  # TODO: Implement grain lookup by ID via AirGapAPI
        except KeyError:
            return None
    
    def _find_finest_grain(self, grains: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Find the finest grain (LCD) from a list of grains.
        
        Uses the grain_level hierarchy to determine which grain is finest.
        Returns the grain with the highest hierarchy number.
        
        Args:
            grains: List of GRAIN dictionaries
        
        Returns:
            The finest GRAIN dictionary (LCD grain)
        """
        if not grains:
            return self._default_grain()
        
        finest_grain = grains[0]
        finest_level = self._get_grain_level_number(finest_grain.get("grain_level", "BASE"))
        
        for grain in grains[1:]:
            level = self._get_grain_level_number(grain.get("grain_level", "BASE"))
            if level > finest_level:
                finest_level = level
                finest_grain = grain
        
        return finest_grain
    
    def _is_grain_finer(self, grain1: Dict[str, Any], grain2: Dict[str, Any]) -> bool:
        """
        Check if grain1 is finer than grain2.
        
        Args:
            grain1: First GRAIN dictionary
            grain2: Second GRAIN dictionary
        
        Returns:
            True if grain1 is finer than grain2
        """
        level1 = self._get_grain_level_number(grain1.get("grain_level", "BASE"))
        level2 = self._get_grain_level_number(grain2.get("grain_level", "BASE"))
        return level1 > level2
    
    def _get_grain_level_number(self, grain_level: str) -> int:
        """
        Get the hierarchy number for a grain level.
        
        Returns the hierarchy number from GRAIN_LEVEL_HIERARCHY, or 0 (BASE)
        if grain_level is not in the hierarchy.
        
        Args:
            grain_level: Grain level string (e.g., "DAY", "ORDER_LINE")
        
        Returns:
            Hierarchy number (higher = finer)
        """
        return self.GRAIN_LEVEL_HIERARCHY.get(grain_level.upper(), 0)
    
    def _get_group_by_fields(self, grain: Dict[str, Any]) -> List[str]:
        """
        Get the list of fields to use for GROUP BY clause.
        
        Uses grain.grouping_fields if available, otherwise falls back to
        the entity's primary_key_field.
        
        Args:
            grain: GRAIN dictionary
        
        Returns:
            List of field names for GROUP BY clause
        """
        # Try grouping_fields from grain first
        grouping_fields = grain.get("grouping_fields")
        if grouping_fields and isinstance(grouping_fields, list):
            return grouping_fields
        
        # Fall back to entity's primary key
        entity_id = grain.get("entity_id")
        if entity_id:
            try:
                entities = self.api.get_all_entities()
                entity = next((e for e in entities if e.get("entity_id") == entity_id), None)
                if entity:
                    primary_key = entity.get("primary_key_field")
                    if primary_key:
                        return [primary_key]
            except (KeyError, AttributeError):
                pass
        
        # Default: empty list (no grouping)
        return []
    
    def _default_grain_context(self) -> Dict[str, Any]:
        """
        Return default grain context for empty input.
        
        Returns:
            Default grain_context dictionary conforming to PLANNER_IO_CONTRACT
        """
        return {
            "grain_id": "grain:base",
            "grain_level": "BASE",
            "grouping_fields": [],
            "aggregation_required": False,
        }
    
    def _default_grain(self) -> Dict[str, Any]:
        """
        Return default grain dictionary.
        
        Returns:
            Default GRAIN dictionary
        """
        return {
            "grain_id": "grain:base",
            "grain_level": "BASE",
            "entity_id": "",
            "grouping_fields": [],
        }

