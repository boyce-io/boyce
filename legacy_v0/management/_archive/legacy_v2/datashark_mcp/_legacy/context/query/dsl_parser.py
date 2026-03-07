"""
Query DSL Parser

Parses declarative query language into structured AST.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from enum import Enum


class QueryType(Enum):
    """Query operation types."""
    FIND = "FIND"
    PATH = "PATH"
    SEARCH = "SEARCH"


@dataclass
class Filter:
    """Query filter."""
    field: str
    operator: str  # '=', '~', 'IN'
    value: Any


@dataclass
class QueryAST:
    """Parsed query AST."""
    query_type: QueryType
    entity_type: Optional[str] = None  # ENTITY, METRIC, etc.
    filters: List[Filter] = None
    path_from: Optional[str] = None
    path_to: Optional[str] = None
    search_term: Optional[str] = None
    
    def __post_init__(self):
        if self.filters is None:
            self.filters = []


class DSLParser:
    """Simple parser for query DSL."""
    
    def parse(self, query: str) -> QueryAST:
        """
        Parse query string into AST.
        
        Args:
            query: Query string (e.g., "FIND ENTITY WHERE system='database'")
            
        Returns:
            QueryAST object
        """
        query = query.strip()
        query_upper = query.upper()
        
        # FIND queries
        if query_upper.startswith("FIND"):
            return self._parse_find(query)
        
        # PATH queries
        if query_upper.startswith("PATH"):
            return self._parse_path(query)
        
        # SEARCH queries
        if query_upper.startswith("SEARCH"):
            return self._parse_search(query)
        
        raise ValueError(f"Unknown query type: {query}")
    
    def _parse_find(self, query: str) -> QueryAST:
        """Parse FIND query."""
        # Simple parsing - "FIND ENTITY WHERE system='database' AND name~'revenue'"
        parts = query.split()
        
        if len(parts) < 2:
            raise ValueError("FIND query must specify entity type")
        
        entity_type = parts[1]
        filters = []
        
        # Parse WHERE clause
        if "WHERE" in query.upper():
            where_pos = query.upper().index("WHERE")
            where_clause = query[where_pos + 5:].strip()
            
            # Parse filters (simple: field='value' or field~'pattern')
            for condition in where_clause.split("AND"):
                condition = condition.strip()
                if "=" in condition:
                    field, value = condition.split("=", 1)
                    field = field.strip()
                    value = value.strip().strip("'\"")
                    filters.append(Filter(field=field, operator="=", value=value))
                elif "~" in condition:
                    field, pattern = condition.split("~", 1)
                    field = field.strip()
                    pattern = pattern.strip().strip("'\"")
                    filters.append(Filter(field=field, operator="~", value=pattern))
                elif "IN" in condition.upper():
                    # field IN ['value1', 'value2']
                    field = condition.split()[0].strip()
                    # Extract list values
                    start = condition.find("[")
                    end = condition.find("]")
                    if start >= 0 and end >= 0:
                        values_str = condition[start + 1:end]
                        values = [v.strip().strip("'\"") for v in values_str.split(",")]
                        filters.append(Filter(field=field, operator="IN", value=values))
        
        return QueryAST(
            query_type=QueryType.FIND,
            entity_type=entity_type,
            filters=filters
        )
    
    def _parse_path(self, query: str) -> QueryAST:
        """Parse PATH query."""
        # "PATH FROM 'node1' TO 'node2'"
        parts = query.upper().split()
        
        if "FROM" not in parts or "TO" not in parts:
            raise ValueError("PATH query must have FROM and TO")
        
        from_idx = parts.index("FROM")
        to_idx = parts.index("TO")
        
        # Extract node IDs (simple: quoted strings)
        from_part = query[query.upper().index("FROM") + 4:query.upper().index("TO")].strip()
        to_part = query[query.upper().index("TO") + 2:].strip()
        
        from_id = from_part.strip("'\"")
        to_id = to_part.strip("'\"")
        
        return QueryAST(
            query_type=QueryType.PATH,
            path_from=from_id,
            path_to=to_id
        )
    
    def _parse_search(self, query: str) -> QueryAST:
        """Parse SEARCH query."""
        # "SEARCH 'term'"
        parts = query.split("'")
        if len(parts) < 2:
            parts = query.split('"')
        
        if len(parts) < 2:
            raise ValueError("SEARCH query must have search term")
        
        search_term = parts[1]
        
        return QueryAST(
            query_type=QueryType.SEARCH,
            search_term=search_term
        )

