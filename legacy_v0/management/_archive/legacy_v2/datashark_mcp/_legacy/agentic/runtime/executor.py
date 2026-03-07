"""
Agentic Executor

Handles plan execution and collects detailed traces.
"""

from __future__ import annotations

import time
from typing import Dict, Any, List
from datashark_mcp.agentic.runtime.planner import Planner
from datashark_mcp.agentic.runtime.context_bridge import ContextBridge


class Executor:
    """Executes plans and collects execution traces."""
    
    def __init__(self, planner: Planner):
        """
        Initialize executor.
        
        Args:
            planner: Planner instance
        """
        self.planner = planner
        self.traces: List[Dict[str, Any]] = []
    
    def execute(self, user_query: str) -> Dict[str, Any]:
        """
        Execute user query and collect trace.
        
        Args:
            user_query: Natural language query
            
        Returns:
            Dict with: results, plan_steps, runtime_ms, trace
        """
        trace = {
            "query": user_query,
            "steps": [],
            "nodes_visited": [],
            "paths_explored": [],
            "timings": {},
            "confidence_metrics": {}
        }
        
        start_time = time.time()
        
        # Execute plan
        plan_result = self.planner.plan(user_query)
        
        # Collect trace data
        trace["steps"] = plan_result["plan_steps"]
        trace["timings"]["total_ms"] = plan_result["runtime_ms"]
        trace["timings"]["translation_ms"] = 0  # Would be measured in full implementation
        trace["timings"]["execution_ms"] = plan_result["runtime_ms"]
        
        # Extract nodes from results
        results = plan_result.get("results", {})
        if results:
            if "nodes" in results:
                trace["nodes_visited"] = [n.get("id") for n in results["nodes"] if isinstance(n, dict)]
            
            # Extract paths
            if "path" in results:
                path = results["path"]
                if path:
                    trace["paths_explored"] = [e.get("id") for e in path.get("path", []) if isinstance(e, dict)]
        
        trace["confidence_metrics"] = {
            "result_count": results.get("count", 0),
            "path_found": bool(results.get("path"))
        }
        
        # Store trace
        self.traces.append(trace)
        
        return {
            "results": plan_result.get("results", {}),
            "plan_steps": plan_result.get("plan_steps", []),
            "runtime_ms": plan_result.get("runtime_ms", 0),
            "trace": trace,
            "explanation": plan_result.get("explanation", ""),
            "dsl_query": plan_result.get("dsl_query", "")
        }
    
    def get_traces(self) -> List[Dict[str, Any]]:
        """Get all execution traces."""
        return self.traces.copy()

