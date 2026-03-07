"""
Explanation Formatter

Renders traces into Markdown and JSON formats.
"""

from __future__ import annotations

import json
from typing import Dict, Any, List
from datashark_mcp.agentic.explain.tracer import Tracer


class ExplanationFormatter:
    """Formats traces into human-readable explanations."""
    
    @staticmethod
    def to_markdown(tracer: Tracer) -> str:
        """
        Render trace as Markdown.
        
        Args:
            tracer: Tracer instance
            
        Returns:
            Markdown string
        """
        trace = tracer.get_trace()
        summary = tracer.get_summary()
        
        md = []
        md.append("# Reasoning Trace\n\n")
        md.append(f"**Total Steps:** {summary['total_steps']}\n")
        md.append(f"**Total Duration:** {summary['total_duration_ms']:.2f}ms\n")
        md.append(f"**Average Confidence:** {summary['avg_confidence']:.2f}\n\n")
        
        md.append("## Steps\n\n")
        for step in trace:
            md.append(f"### Step {step['step_number']}: {step['operation']}\n\n")
            md.append(f"- **Duration:** {step['duration_ms']:.2f}ms\n")
            md.append(f"- **Confidence:** {step['confidence']:.2f}\n")
            
            if step.get("node_context"):
                md.append(f"- **Node:** {step['node_context']}\n")
            if step.get("edge_context"):
                md.append(f"- **Edge:** {step['edge_context']}\n")
            
            if step.get("input_params"):
                md.append(f"- **Input:** {json.dumps(step['input_params'], indent=2)}\n")
            
            md.append("\n")
        
        return "".join(md)
    
    @staticmethod
    def to_json(tracer: Tracer) -> Dict[str, Any]:
        """
        Render trace as JSON.
        
        Args:
            tracer: Tracer instance
            
        Returns:
            JSON-serializable dict
        """
        trace = tracer.get_trace()
        summary = tracer.get_summary()
        
        return {
            "summary": summary,
            "steps": trace,
            "cause_effect_links": ExplanationFormatter._extract_cause_effect(trace),
            "semantic_concepts": ExplanationFormatter._extract_concepts(trace)
        }
    
    @staticmethod
    def _extract_cause_effect(trace: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract cause-effect links from trace."""
        links = []
        for i, step in enumerate(trace):
            if i > 0:
                prev_step = trace[i - 1]
                links.append({
                    "cause": prev_step["operation"],
                    "effect": step["operation"],
                    "step_from": prev_step["step_number"],
                    "step_to": step["step_number"]
                })
        return links
    
    @staticmethod
    def _extract_concepts(trace: List[Dict[str, Any]]) -> List[str]:
        """Extract semantic concepts mentioned in trace."""
        concepts = set()
        for step in trace:
            # Extract concepts from node/edge contexts
            if step.get("node_context"):
                node_id = step["node_context"]
                if "concept" in node_id.lower():
                    concepts.add(node_id)
        return sorted(list(concepts))

