"""
Reasoning Tracer

Captures detailed reasoning traces from planner/executor.
"""

from __future__ import annotations

import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class TraceStep:
    """A single step in reasoning trace."""
    step_number: int
    operation: str
    node_context: Optional[str] = None  # Node ID involved
    edge_context: Optional[str] = None  # Edge ID involved
    input_params: Dict[str, Any] = field(default_factory=dict)
    result: Any = None
    duration_ms: float = 0.0
    confidence: float = 1.0
    rule_matches: List[str] = field(default_factory=list)  # Rule patterns that matched
    step_id: Optional[str] = None  # Unique step identifier


class Tracer:
    """Captures and stores reasoning traces."""
    
    def __init__(self):
        """Initialize tracer."""
        self.trace: List[TraceStep] = []
        self.start_time: Optional[float] = None
    
    def start(self) -> None:
        """Start tracing."""
        self.trace = []
        self.start_time = time.time()
    
    def add_step(
        self,
        step_number: int,
        operation: str,
        node_context: Optional[str] = None,
        edge_context: Optional[str] = None,
        input_params: Optional[Dict[str, Any]] = None,
        result: Any = None,
        duration_ms: float = 0.0,
        confidence: float = 1.0,
        rule_matches: Optional[List[str]] = None,
        step_id: Optional[str] = None
    ) -> None:
        """
        Add a trace step.
        
        Args:
            step_number: Step number
            operation: Operation name
            node_context: Node ID involved
            edge_context: Edge ID involved
            input_params: Input parameters
            result: Operation result
            duration_ms: Duration in milliseconds
            confidence: Confidence score
        """
        step = TraceStep(
            step_number=step_number,
            operation=operation,
            node_context=node_context,
            edge_context=edge_context,
            input_params=input_params or {},
            result=result,
            duration_ms=duration_ms,
            confidence=confidence,
            rule_matches=rule_matches or [],
            step_id=step_id or f"step_{step_number}"
        )
        self.trace.append(step)
    
    def get_trace(self, normalize_timestamps: bool = False) -> List[Dict[str, Any]]:
        """
        Get trace as list of dicts with structured step data.
        
        Args:
            normalize_timestamps: If True, normalize timestamps for deterministic hashing
        """
        from datashark_mcp.context.determinism import normalize_timestamp
        
        steps = []
        for s in self.trace:
            step_dict = {
                "step_id": s.step_id or f"step_{s.step_number}",
                "step_number": s.step_number,
                "operation": s.operation,
                "node_context": s.node_context,
                "edge_context": s.edge_context,
                "input_params": s.input_params,
                "result": s.result,
                "duration_ms": round(s.duration_ms, 2),  # Round to 2 decimals for stability
                "confidence": round(s.confidence, 2),  # Round to 2 decimals for stability
                "rule_matches": sorted(s.rule_matches) if s.rule_matches else [],  # Sort for determinism
            }
            
            # Add timestamp (normalized if requested)
            if normalize_timestamps:
                # Use step content for deterministic timestamp
                step_content = f"{s.step_number}:{s.operation}:{s.node_context or ''}"
                step_dict["timestamp"] = normalize_timestamp(datetime.now(timezone.utc).isoformat(), content=step_content)
            else:
                step_dict["timestamp"] = datetime.now(timezone.utc).isoformat()
            
            steps.append(step_dict)
        
        return steps
    
    def get_summary(self) -> Dict[str, Any]:
        """Get trace summary with normalized numeric values."""
        total_duration = sum(s.duration_ms for s in self.trace)
        avg_confidence = sum(s.confidence for s in self.trace) / len(self.trace) if self.trace else 0.0
        
        return {
            "total_steps": len(self.trace),
            "total_duration_ms": round(total_duration, 2),  # Round to 2 decimals
            "avg_confidence": round(avg_confidence, 2),  # Round to 2 decimals
            "nodes_visited": len(set(s.node_context for s in self.trace if s.node_context)),
            "edges_explored": len(set(s.edge_context for s in self.trace if s.edge_context))
        }

