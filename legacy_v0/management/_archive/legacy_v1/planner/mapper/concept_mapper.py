"""
Concept Mapper implementation for translating natural language to semantic concepts.

Implements deterministic concept mapping that translates natural language keywords
into canonical Semantic Snapshot IDs (ENTITY, FIELD, METRIC, FILTER) using
definitions from the SNAPSHOT_SCHEMA_CONTRACT.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set

from datashark_mcp.kernel.air_gap_api import AirGapAPI


class ConceptMapper:
    """
    Concept mapping engine for translating natural language to semantic graph concepts.
    
    Contract:
        - Maps natural language query terms to canonical semantic graph IDs
        - Uses ENTITY, FIELD, METRIC definitions from SNAPSHOT_SCHEMA_CONTRACT
        - Deterministic: same inputs → same outputs
        - Returns concept_map conforming to PLANNER_IO_CONTRACT
        - Uses AirGapAPI interface for graph access (read-only, projected graph only)
    """
    
    def __init__(self, air_gap_api: AirGapAPI) -> None:
        """
        Initialize concept mapper with AirGapAPI.
        
        Args:
            air_gap_api: AirGapAPI instance providing read-only access to the
                ProjectedGraph. This ensures the Safety Kernel boundary is maintained.
        """
        self.api = air_gap_api
        # Build lookup indices for efficient matching
        self._entity_index: Dict[str, Dict[str, Any]] = {}
        self._field_index: Dict[str, Dict[str, Any]] = {}
        self._metric_index: Dict[str, Dict[str, Any]] = {}
        self._valid_values_index: Dict[str, Dict[str, Any]] = {}  # For smart filter matching
        self._build_indices()
    
    def map_query_to_concepts(self, query_input: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Map natural language query to semantic graph concepts.
        
        Performs pattern matching and string search to extract canonical names
        and map them to corresponding IDs in the Semantic Graph. Uses simple
        regex and string matching for initial implementation.
        
        Contract:
            - Extracts entities, metrics, filters, and dimensions from query
            - Maps terms to canonical IDs from semantic graph
            - Returns concept_map conforming to PLANNER_IO_CONTRACT
            - Deterministic: same inputs → same outputs
            - Returns empty lists if no concepts identified
        
        Args:
            query_input: Raw natural language query string
        
        Returns:
            Dictionary conforming to PLANNER_IO_CONTRACT concept_map schema:
            - entities (list[dict]): List of entity mappings
            - metrics (list[dict]): List of metric mappings
            - filters (list[dict]): List of filter mappings
            - dimensions (list[dict]): List of dimension mappings
        
        Example:
            >>> mapper = ConceptMapper(semantic_graph)
            >>> result = mapper.map_query_to_concepts("Show me total sales by region")
            >>> result
            {
                "entities": [{"term": "sales", "entity_id": "entity:sales", "entity_name": "sales"}],
                "metrics": [{"term": "total sales", "metric_id": "metric:total_sales", "metric_name": "total_sales"}],
                "filters": [],
                "dimensions": [{"term": "region", "field_id": "field:sales:region", "field_name": "region"}]
            }
        """
        if not query_input or not query_input.strip():
            return self._empty_concept_map()
        
        # Normalize query: lowercase and remove extra whitespace
        normalized_query = re.sub(r'\s+', ' ', query_input.lower().strip())
        
        # Extract concepts using pattern matching
        entities = self._extract_entities(normalized_query)
        metrics = self._extract_metrics(normalized_query)
        filters = self._extract_filters(normalized_query)
        dimensions = self._extract_dimensions(normalized_query)
        
        return {
            "entities": entities,
            "metrics": metrics,
            "filters": filters,
            "dimensions": dimensions,
        }
    
    def _build_indices(self) -> None:
        """
        Build lookup indices from semantic graph for efficient matching.
        
        Creates dictionaries mapping canonical names and aliases to their
        corresponding ENTITY, FIELD, and METRIC dictionaries.
        Also builds a valid_values index for smart filter matching.
        """
        self._valid_values_index: Dict[str, Dict[str, Any]] = {}  # column_name -> {field_info, valid_values}
        
        try:
            # Index entities
            entities = self.api.get_all_entities()
            for entity in entities:
                entity_name = entity.get("entity_name", "").lower()
                entity_id = entity.get("entity_id", "")
                if entity_name and entity_id:
                    self._entity_index[entity_name] = entity
                    # Also index plural forms and common variations
                    if entity_name.endswith("s"):
                        singular = entity_name[:-1]
                        self._entity_index[singular] = entity
                    else:
                        plural = entity_name + "s"
                        self._entity_index[plural] = entity
            
            # Index fields (need to iterate through entities)
            for entity in entities:
                entity_id = entity.get("entity_id", "")
                if entity_id:
                    try:
                        fields = self.api.get_fields_by_entity(entity_id)
                        for field in fields:
                            field_name = field.get("field_name", "").lower()
                            column_name = field.get("column_name", "").lower()
                            field_id = field.get("field_id", "")
                            
                            if field_name and field_id:
                                # Store with entity context for disambiguation
                                key = f"{entity.get('entity_name', '').lower()}:{field_name}"
                                self._field_index[key] = field
                                # Also index by field name alone
                                self._field_index[field_name] = field
                            
                            # Index valid_values for smart filter matching
                            valid_values = field.get("valid_values", [])
                            if valid_values:
                                # Index by column_name (preferred) or field_name
                                index_key = column_name if column_name else field_name
                                if index_key:
                                    self._valid_values_index[index_key.lower()] = {
                                        "field": field,
                                        "entity": entity,
                                        "valid_values": valid_values,
                                        "column_name": column_name or field_name
                                    }
                    except KeyError:
                        # Entity not found, skip
                        continue
            
            # Index metrics (need to get all grains first, then metrics by grain)
            # For now, we'll build a basic index - full implementation would require
            # get_all_grains() or similar method on SemanticGraph
            # This is a placeholder that can be extended when SemanticGraph API is complete
            
        except (KeyError, AttributeError):
            # Graph not fully initialized, indices will be empty
            pass
    
    def _extract_entities(self, query: str) -> List[Dict[str, Any]]:
        """
        Extract entity references from query.
        
        Uses pattern matching to identify entity names in the query and
        maps them to canonical entity IDs from the semantic graph.
        
        Args:
            query: Normalized query string
        
        Returns:
            List of entity mapping dictionaries with term, entity_id, entity_name
        """
        entities: List[Dict[str, Any]] = []
        matched_terms: Set[str] = set()
        
        # Search for entity names in query
        for entity_name, entity in self._entity_index.items():
            # Use word boundary matching to avoid partial matches
            pattern = r'\b' + re.escape(entity_name) + r'\b'
            if re.search(pattern, query, re.IGNORECASE):
                # Avoid duplicates
                if entity_name not in matched_terms:
                    entities.append({
                        "term": entity_name,
                        "entity_id": entity.get("entity_id", ""),
                        "entity_name": entity.get("entity_name", ""),
                    })
                    matched_terms.add(entity_name)
        
        return entities
    
    def _extract_metrics(self, query: str) -> List[Dict[str, Any]]:
        """
        Extract metric references from query.
        
        Uses pattern matching to identify metric names and common metric
        keywords (e.g., "total", "sum", "average", "count") in the query.
        
        Args:
            query: Normalized query string
        
        Returns:
            List of metric mapping dictionaries with term, metric_id, metric_name
        """
        metrics: List[Dict[str, Any]] = []
        matched_terms: Set[str] = set()
        
        # Common metric keywords
        metric_keywords = [
            r'\btotal\b',
            r'\bsum\b',
            r'\baverage\b',
            r'\bavg\b',
            r'\bcount\b',
            r'\bmaximum\b',
            r'\bmax\b',
            r'\bminimum\b',
            r'\bmin\b',
            r'\brevenue\b',
            r'\bsales\b',
            r'\bprofit\b',
            r'\bamount\b',
        ]
        
        # Search for metric keywords
        for keyword_pattern in metric_keywords:
            if re.search(keyword_pattern, query, re.IGNORECASE):
                # Extract the term (word or phrase containing the keyword)
                match = re.search(keyword_pattern, query, re.IGNORECASE)
                if match:
                    # Try to extract a phrase (e.g., "total sales")
                    start = max(0, match.start() - 10)
                    end = min(len(query), match.end() + 10)
                    context = query[start:end]
                    # Extract words around the keyword
                    words = re.findall(r'\b\w+\b', context)
                    term = ' '.join(words).lower()
                    
                    if term and term not in matched_terms:
                        # For now, create a placeholder metric mapping
                        # Full implementation would match against actual metrics in graph
                        metrics.append({
                            "term": term,
                            "metric_id": f"metric:{term.replace(' ', '_')}",
                            "metric_name": term.replace(' ', '_'),
                        })
                        matched_terms.add(term)
        
        # Search for explicit metric names from index
        for metric_name, metric in self._metric_index.items():
            pattern = r'\b' + re.escape(metric_name) + r'\b'
            if re.search(pattern, query, re.IGNORECASE):
                if metric_name not in matched_terms:
                    metrics.append({
                        "term": metric_name,
                        "metric_id": metric.get("metric_id", ""),
                        "metric_name": metric.get("metric_name", ""),
                    })
                    matched_terms.add(metric_name)
        
        return metrics
    
    def _extract_filters(self, query: str) -> List[Dict[str, Any]]:
        """
        Extract filter conditions from query using smart matching against valid_values.
        
        Uses two strategies:
        1. Smart matching: Scans user input for tokens that match known valid_values in schema
        2. Pattern matching: Traditional regex patterns for explicit filter expressions
        
        Args:
            query: Normalized query string
        
        Returns:
            List of filter mapping dictionaries with field, operator, value (NO sql_expression)
        """
        raw_filters: List[Dict[str, Any]] = []
        matched_terms: Set[str] = set()
        
        # Strategy 1: Smart filter extraction (match tokens against valid_values)
        smart_filters = self._extract_smart_filters(query)
        for filter_item in smart_filters:
            # Avoid duplicates
            filter_key = f"{filter_item.get('field', '')}={filter_item.get('value', '')}"
            if filter_key not in matched_terms:
                raw_filters.append(filter_item)
                matched_terms.add(filter_key)
        
        # Strategy 2: Pattern-based filter extraction (explicit filter expressions)
        filter_patterns = [
            # Date filters: "in 2024", "last month", "this year"
            (r'\b(in|during|for)\s+(\d{4})\b', self._build_date_filter),
            (r'\b(last|this|next)\s+(year|month|week|day|quarter)\b', self._build_relative_date_filter),
            # Equality filters: "equals X", "is X", "= X"
            (r'\b(equals?|is|=\s*)\s*(["\']?)(\w+)\2\b', self._build_equality_filter),
            # Range filters: "greater than X", "less than Y"
            (r'\b(greater|more|>\s*)\s*than\s+(\d+)\b', self._build_range_filter),
            (r'\b(less|fewer|<\s*)\s*than\s+(\d+)\b', self._build_range_filter),
            # IN filters: "in (X, Y, Z)"
            (r'\bin\s*\(([^)]+)\)\b', self._build_in_filter),
        ]
        
        for pattern, builder_func in filter_patterns:
            matches = re.finditer(pattern, query, re.IGNORECASE)
            for match in matches:
                term = match.group(0)
                if term not in matched_terms:
                    # Try to build filter expression
                    filter_expr = builder_func(match, query)
                    if filter_expr:
                        filter_key = f"{filter_expr.get('field', '')}={filter_expr.get('value', '')}"
                        if filter_key not in matched_terms:
                            raw_filters.append(filter_expr)
                            matched_terms.add(filter_key)
                            matched_terms.add(term)
        
        # Merge filters: Combine same-field filters into IN clauses
        merged_filters = self._merge_filters(raw_filters)
        return merged_filters
    
    def _merge_filters(self, raw_filters: List[Dict]) -> List[Dict]:
        """
        Merge filters by field name AND operator.
        
        Turns [{'field': 'region', 'operator': '=', 'value': 'NY'}, {'field': 'region', 'operator': '=', 'value': 'CA'}] 
        Into  [{'field': 'region', 'operator': 'IN', 'value': ['NY', 'CA']}]
        
        CRITICAL: Only merges filters with the SAME operator. Filters with different operators
        (e.g., '=' and '!=') must remain separate.
        
        Args:
            raw_filters: List of raw filter dictionaries with 'field', 'operator', and 'value' keys
        
        Returns:
            List of merged filter dictionaries with combined values using IN operator
        """
        # Group by (field, operator) tuple to prevent merging different operators
        grouped = {}
        
        # 1. Group values by (field, operator) combination
        for f in raw_filters:
            field = f.get('field') or f.get('field_name')  # Support both keys
            operator = f.get('operator', '=')  # Default to '=' if not specified
            if not field:
                continue
            
            # Use (field, operator) as key to prevent cross-operator merging
            key = (field, operator)
            if key not in grouped:
                grouped[key] = []
            
            value = f.get('value')
            if value:
                grouped[key].append(value)
        
        # 2. Rebuild the list with correct operators
        final_filters = []
        for (field, operator), values in grouped.items():
            # Deduplicate values while preserving order
            seen = set()
            unique_values = []
            for v in values:
                if v not in seen:
                    seen.add(v)
                    unique_values.append(v)
            
            if len(unique_values) > 1:
                # Multiple values = IN clause (only for equality operators)
                if operator == '=':
                    final_filters.append({
                        "field": field,
                        "operator": "IN",
                        "value": unique_values  # List of deduplicated values
                    })
                else:
                    # Non-equality operators cannot be merged into IN
                    # Keep as separate filters
                    for value in unique_values:
                        final_filters.append({
                            "field": field,
                            "operator": operator,
                            "value": value
                        })
            else:
                # Single value = use original operator
                final_filters.append({
                    "field": field,
                    "operator": operator,
                    "value": unique_values[0]
                })
        
        return final_filters
    
    def _extract_smart_filters(self, query: str) -> List[Dict[str, Any]]:
        """
        Extract filters by matching user input tokens against known valid_values in schema.
        
        Scans the query for tokens that match valid_values defined in column metadata.
        This enables smart filter extraction without requiring explicit filter syntax.
        
        Args:
            query: Normalized query string
        
        Returns:
            List of filter dictionaries with field, operator, value (NO sql_expression)
        """
        filters: List[Dict[str, Any]] = []
        
        # Tokenize query (split on whitespace and punctuation)
        # Keep both individual tokens and potential multi-word values
        tokens = re.findall(r'\b\w+\b', query.lower())
        
        # Also check for quoted strings (exact matches)
        quoted_strings = re.findall(r'["\']([^"\']+)["\']', query)
        
        # Combine tokens and quoted strings
        all_tokens = tokens + [q.lower() for q in quoted_strings]
        
        # Iterate through all columns with valid_values
        for column_key, column_info in self._valid_values_index.items():
            field = column_info["field"]
            entity = column_info["entity"]
            valid_values = column_info["valid_values"]
            column_name = column_info["column_name"]
            
            # Check if any token matches a valid value (case-insensitive)
            for token in all_tokens:
                for valid_val in valid_values:
                    # Exact match (case-insensitive)
                    if token == valid_val.lower():
                        # Found a match! Create filter (NO sql_expression - hardening)
                        field_name = field.get("field_name", column_name)
                        field_id = field.get("field_id", "")
                        entity_name = entity.get("entity_name", "")
                        
                        filters.append({
                            "term": token,
                            "field_id": field_id,
                            "field": field_name,  # Use 'field' for consistency
                            "field_name": field_name,  # Keep for backward compatibility
                            "column_name": column_name,
                            "operator": "=",
                            "value": valid_val,  # Use canonical casing from metadata
                            "entity_name": entity_name
                            # NO sql_expression - removed per hardening refactor
                        })
                        break  # Found match for this token, move to next token
        
        return filters
    
    def _extract_dimensions(self, query: str) -> List[Dict[str, Any]]:
        """
        Extract dimension references from query.
        
        Uses pattern matching to identify dimension names (often appearing
        after "by", "group by", "for each") and maps them to field IDs.
        
        Args:
            query: Normalized query string
        
        Returns:
            List of dimension mapping dictionaries with term, field_id, field_name
        """
        dimensions: List[Dict[str, Any]] = []
        matched_terms: Set[str] = set()
        
        # Look for "by X" or "group by X" patterns
        by_pattern = r'\b(?:group\s+)?by\s+(\w+(?:\s+\w+)*)\b'
        matches = re.finditer(by_pattern, query, re.IGNORECASE)
        for match in matches:
            dimension_term = match.group(1).strip().lower()
            if dimension_term and dimension_term not in matched_terms:
                # Try to find matching field
                field = self._find_field_by_name(dimension_term)
                if field:
                    dimensions.append({
                        "term": dimension_term,
                        "field_id": field.get("field_id", ""),
                        "field_name": field.get("field_name", ""),
                    })
                    matched_terms.add(dimension_term)
        
        # Also search for field names directly in query
        for field_key, field in self._field_index.items():
            # Extract field name (remove entity prefix if present)
            field_name = field_key.split(':')[-1] if ':' in field_key else field_key
            pattern = r'\b' + re.escape(field_name) + r'\b'
            if re.search(pattern, query, re.IGNORECASE):
                if field_name not in matched_terms:
                    dimensions.append({
                        "term": field_name,
                        "field_id": field.get("field_id", ""),
                        "field_name": field.get("field_name", ""),
                    })
                    matched_terms.add(field_name)
        
        return dimensions
    
    def _find_field_by_name(self, field_name: str) -> Dict[str, Any] | None:
        """
        Find a field by name in the field index.
        
        Args:
            field_name: Field name to search for
        
        Returns:
            Field dictionary or None if not found
        """
        # Try exact match first
        if field_name in self._field_index:
            return self._field_index[field_name]
        
        # Try partial match
        for key, field in self._field_index.items():
            if field_name in key or key in field_name:
                return field
        
        return None
    
    def _build_date_filter(self, match: re.Match[str], query: str) -> Dict[str, Any] | None:
        """Build a date filter expression from match."""
        # Placeholder: would need field context to build proper SQL
        return None
    
    def _build_relative_date_filter(self, match: re.Match[str], query: str) -> Dict[str, Any] | None:
        """Build a relative date filter expression from match."""
        # Placeholder: would need field context to build proper SQL
        return None
    
    def _build_equality_filter(self, match: re.Match[str], query: str) -> Dict[str, Any] | None:
        """Build an equality filter expression from match."""
        # Placeholder: would need field context to build proper SQL
        return None
    
    def _build_range_filter(self, match: re.Match[str], query: str) -> Dict[str, Any] | None:
        """Build a range filter expression from match."""
        # Placeholder: would need field context to build proper SQL
        return None
    
    def _build_in_filter(self, match: re.Match[str], query: str) -> Dict[str, Any] | None:
        """Build an IN filter expression from match."""
        # Placeholder: would need field context to build proper SQL
        return None
    
    def _empty_concept_map(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Return empty concept map structure.
        
        Returns:
            Empty concept_map dictionary with empty lists
        """
        return {
            "entities": [],
            "metrics": [],
            "filters": [],
            "dimensions": [],
        }

