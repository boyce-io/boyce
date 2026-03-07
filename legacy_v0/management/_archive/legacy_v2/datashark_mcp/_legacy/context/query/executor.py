"""
Query DSL Executor

Executes parsed AST using Context API and GraphStore.
"""

from __future__ import annotations

import json
from typing import Dict, Any, List
from datashark_mcp.context.api import ContextAPI
from datashark_mcp.context.query.dsl_parser import QueryAST, QueryType
from datashark_mcp.context.enrichment.semantic_enricher import SemanticEnricher


class QueryExecutor:
    """Executes query AST and returns results."""
    
    def __init__(self, api: ContextAPI, enricher: SemanticEnricher = None):
        """
        Initialize executor.
        
        Args:
            api: ContextAPI instance
            enricher: Optional SemanticEnricher for semantic expansion
        """
        self.api = api
        self.enricher = enricher
    
    def execute(self, ast: QueryAST, semantic_expansion: bool = False) -> Dict[str, Any]:
        """
        Execute query AST.
        
        Args:
            ast: Parsed query AST
            semantic_expansion: If True, expand results using semantic enrichment
            
        Returns:
            Dict with results: nodes, edges, stats
        """
        if ast.query_type == QueryType.FIND:
            return self._execute_find(ast, semantic_expansion)
        elif ast.query_type == QueryType.PATH:
            return self._execute_path(ast)
        elif ast.query_type == QueryType.SEARCH:
            return self._execute_search(ast, semantic_expansion)
        else:
            raise ValueError(f"Unknown query type: {ast.query_type}")
    
    def _execute_find(self, ast: QueryAST, semantic_expansion: bool) -> Dict[str, Any]:
        """Execute FIND query."""
        # Build filters dict
        filters = {}
        for filter_obj in ast.filters:
            if filter_obj.operator == "=":
                if filter_obj.field not in filters:
                    filters[filter_obj.field] = []
                if isinstance(filter_obj.value, list):
                    filters[filter_obj.field].extend(filter_obj.value)
                else:
                    filters[filter_obj.field].append(filter_obj.value)
            elif filter_obj.operator == "IN":
                filters[filter_obj.field] = filter_obj.value
        
        # Execute query
        if "system" in filters:
            results = []
            for system in filters["system"]:
                entities = self.api.find_entities_by_system(system)
                results.extend(entities)
        elif "repo" in filters:
            results = []
            for repo in filters["repo"]:
                entities = self.api.find_entities_by_repo(repo)
                results.extend(entities)
        else:
            # Search all
            results = self.api.search("", filters=filters if filters else None)
        
        # Apply additional filters
        filtered_results = []
        for node in results:
            if ast.entity_type and node.type != ast.entity_type:
                continue
            
            # Apply pattern filters
            matches = True
            for filter_obj in ast.filters:
                if filter_obj.operator == "~":
                    field_value = getattr(node, filter_obj.field, None) or node.attributes.get(filter_obj.field, "")
                    if filter_obj.value.lower() not in str(field_value).lower():
                        matches = False
                        break
            
            if matches:
                filtered_results.append(node)
        
        # Semantic expansion
        expanded_nodes = []
        expanded_edges = []
        if semantic_expansion and self.enricher:
            # Note: This would require enriching before querying
            pass  # Placeholder for semantic expansion
        
        return {
            "nodes": [node.to_dict() for node in filtered_results],
            "edges": expanded_edges,
            "stats": {
                "count": len(filtered_results),
                "query_type": "FIND",
                "semantic_expansion": semantic_expansion
            }
        }
    
    def _execute_path(self, ast: QueryAST) -> Dict[str, Any]:
        """Execute PATH query."""
        if not ast.path_from or not ast.path_to:
            return {
                "nodes": [],
                "edges": [],
                "path": [],
                "stats": {
                    "found": False,
                    "query_type": "PATH"
                }
            }
        
        path_result = self.api.find_join_path(ast.path_from, ast.path_to)
        
        if path_result:
            return {
                "nodes": [],
                "edges": [edge.to_dict() for edge in path_result["path"]],
                "path": path_result,
                "stats": {
                    "found": True,
                    "depth": path_result["depth"],
                    "query_type": "PATH"
                }
            }
        else:
            return {
                "nodes": [],
                "edges": [],
                "path": None,
                "stats": {
                    "found": False,
                    "query_type": "PATH"
                }
            }
    
    def _execute_search(self, ast: QueryAST, semantic_expansion: bool) -> Dict[str, Any]:
        """Execute SEARCH query."""
        results = self.api.search(ast.search_term or "")
        
        return {
            "nodes": [node.to_dict() for node in results],
            "edges": [],
            "stats": {
                "count": len(results),
                "query_type": "SEARCH",
                "semantic_expansion": semantic_expansion
            }
        }

