"""
Evaluation Suite

Runs evaluation on NL→DSL→execution test cases.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict, Any
from datashark_mcp.agentic.evaluation.metrics import compute_metrics, EvaluationMetrics
from datashark_mcp.agentic.runtime.executor import Executor
from datashark_mcp.agentic.runtime.planner import Planner
from datashark_mcp.agentic.runtime.context_bridge import ContextBridge
from datashark_mcp.context.api import ContextAPI
from datashark_mcp.context.store import GraphStore


class Evaluator:
    """Evaluates agentic reasoning on test suite."""
    
    def __init__(self, store: GraphStore, api: ContextAPI, bridge: ContextBridge):
        """
        Initialize evaluator.
        
        Args:
            store: GraphStore instance
            api: ContextAPI instance
            bridge: ContextBridge instance
        """
        self.store = store
        self.api = api
        self.bridge = bridge
        self.planner = Planner(bridge, seed=42)
        self.executor = Executor(self.planner)
    
    def evaluate(self, test_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Evaluate on test cases.
        
        Args:
            test_cases: List of test cases with:
                - query: Natural language query
                - expected_dsl: Expected DSL query (optional)
                - expected_concepts: Expected concept names (optional)
        
        Returns:
            Dict with metrics and results
        """
        actual_results = []
        
        for test_case in test_cases:
            query = test_case["query"]
            result = self.executor.execute(query)
            actual_results.append(result)
        
        # Compute metrics
        metrics = compute_metrics(test_cases, actual_results)
        
        return {
            "metrics": metrics.to_dict(),
            "test_cases": len(test_cases),
            "results": actual_results
        }
    
    def generate_report(self, evaluation_result: Dict[str, Any], output_file: Path) -> None:
        """
        Generate evaluation report.
        
        Args:
            evaluation_result: Result from evaluate()
            output_file: Path to output markdown file
        """
        metrics = evaluation_result["metrics"]
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("# Evaluation Report\n\n")
            f.write(f"**Test Cases:** {evaluation_result['test_cases']}\n\n")
            
            f.write("## Metrics\n\n")
            f.write(f"- **Accuracy:** {metrics['accuracy']:.3f}\n")
            f.write(f"- **Recall:** {metrics['recall']:.3f}\n")
            f.write(f"- **Latency:** {metrics['latency_ms']:.2f}ms\n")
            f.write(f"- **Reproducibility:** {metrics['reproducibility']:.3f}\n\n")
            
            f.write("## Test Results\n\n")
            for i, result in enumerate(evaluation_result["results"], 1):
                f.write(f"### Test Case {i}\n\n")
                f.write(f"- **Query:** {result.get('trace', {}).get('query', 'N/A')}\n")
                f.write(f"- **DSL:** {result.get('dsl_query', 'N/A')}\n")
                f.write(f"- **Runtime:** {result.get('runtime_ms', 0):.2f}ms\n")
                f.write(f"- **Results:** {result.get('results', {}).get('count', 0)}\n\n")


def run_evaluation_suite(
    store: GraphStore,
    api: ContextAPI,
    bridge: ContextBridge,
    test_cases: List[Dict[str, Any]],
    output_file: Path
) -> EvaluationMetrics:
    """
    Run evaluation suite and generate report.
    
    Args:
        store: GraphStore instance
        api: ContextAPI instance
        bridge: ContextBridge instance
        test_cases: List of test cases
        output_file: Path to output report
        
    Returns:
        EvaluationMetrics
    """
    evaluator = Evaluator(store, api, bridge)
    result = evaluator.evaluate(test_cases)
    evaluator.generate_report(result, output_file)
    
    return EvaluationMetrics(**result["metrics"])

