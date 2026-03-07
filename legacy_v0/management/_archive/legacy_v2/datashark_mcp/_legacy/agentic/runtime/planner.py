"""
Agentic Planner

Implements reasoning loop: translate NL → parse DSL → plan traversal → execute.
"""

from __future__ import annotations

import random
import time
from typing import Dict, Any, List, Optional
from datashark_mcp.agentic.nl2dsl.translator import NLTranslator
from datashark_mcp.context.query.dsl_parser import DSLParser
from datashark_mcp.agentic.runtime.context_bridge import ContextBridge


class Planner:
    """Plans and executes reasoning over the graph."""
    
    def __init__(self, bridge: ContextBridge, seed: int = 42):
        """
        Initialize planner.
        
        Args:
            bridge: ContextBridge instance
            seed: Random seed for deterministic planning
        """
        self.bridge = bridge
        self.translator = NLTranslator(catalog=bridge.catalog)
        self.parser = DSLParser()
        random.seed(seed)
    
    def plan(self, user_query: str) -> Dict[str, Any]:
        """
        Plan and execute reasoning over graph.
        
        Args:
            user_query: Natural language query
            
        Returns:
            Dict with: plan_steps, results, explanation, runtime_ms
        """
        start_time = time.time()
        
        # Step 1: Translate NL → DSL
        dsl_query = self.translator.translate(user_query)
        
        # Step 2: Parse DSL → AST
        ast = self.parser.parse(dsl_query)
        
        # Step 3: Plan execution steps
        plan_steps = self._plan_steps(ast)
        
        # Step 4: Execute plan
        results = self._execute_plan(plan_steps, ast)
        
        # Step 5: Generate explanation
        explanation = self._generate_explanation(plan_steps, results, ast)
        
        runtime_ms = (time.time() - start_time) * 1000
        
        return {
            "plan_steps": plan_steps,
            "results": results,
            "explanation": explanation,
            "runtime_ms": runtime_ms,
            "dsl_query": dsl_query,
            "concepts_found": []  # Placeholder for concept extraction
        }
    
    def _plan_steps(self, ast) -> List[Dict[str, Any]]:
        """Generate execution plan from AST."""
        steps = []
        
        if ast.query_type.value == "FIND":
            steps.append({
                "step": 1,
                "operation": "find_entities",
                "params": {
                    "entity_type": ast.entity_type,
                    "filters": {f.field: f.value for f in ast.filters if f.operator == "="}
                }
            })
        
        elif ast.query_type.value == "PATH":
            steps.append({
                "step": 1,
                "operation": "find_join_path",
                "params": {
                    "src_id": ast.path_from,
                    "dst_id": ast.path_to
                }
            })
        
        elif ast.query_type.value == "SEARCH":
            steps.append({
                "step": 1,
                "operation": "search",
                "params": {
                    "term": ast.search_term
                }
            })
        
        return steps
    
    def _execute_plan(self, plan_steps: List[Dict[str, Any]], ast) -> Dict[str, Any]:
        """Execute plan steps."""
        all_results = []
        
        for step in plan_steps:
            operation = step["operation"]
            params = step["params"]
            
            if operation == "find_entities":
                if "system" in params:
                    results = self.bridge.query("find_entities_by_system", system=params["system"])
                    all_results.extend(results)
                elif "repo" in params:
                    results = self.bridge.query("find_entities_by_repo", repo=params["repo"])
                    all_results.extend(results)
                else:
                    results = self.bridge.query("search", term="", filters=params.get("filters"))
                    all_results.extend(results)
            
            elif operation == "find_join_path":
                result = self.bridge.query(
                    "find_join_path",
                    src_id=params["src_id"],
                    dst_id=params["dst_id"]
                )
                if result:
                    all_results.append(result)
            
            elif operation == "search":
                results = self.bridge.query("search", term=params["term"])
                all_results.extend(results)
        
        return {
            "nodes": [r.to_dict() if hasattr(r, "to_dict") else r for r in all_results[:100]],  # Limit results
            "count": len(all_results)
        }
    
    def _generate_explanation(self, plan_steps: List[Dict[str, Any]], results: Dict[str, Any], ast) -> str:
        """Generate human-readable explanation."""
        explanation_parts = []
        
        explanation_parts.append(f"Query type: {ast.query_type.value}")
        explanation_parts.append(f"Execution steps: {len(plan_steps)}")
        
        if plan_steps:
            step = plan_steps[0]
            explanation_parts.append(f"Operation: {step['operation']}")
        
        explanation_parts.append(f"Results found: {results.get('count', 0)}")
        
        if ast.query_type.value == "PATH":
            explanation_parts.append(f"Path from: {ast.path_from}")
            explanation_parts.append(f"Path to: {ast.path_to}")
        
        return "\n".join(explanation_parts)

