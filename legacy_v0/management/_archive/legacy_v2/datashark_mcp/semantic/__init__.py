"""
Semantic module (wiring shim).

This repo layout provides SemanticGraph as part of the Safety Kernel type system.
Historically, call sites (and placeholder tests) import SemanticGraph from
`datashark_mcp.semantic`.

This module re-exports the canonical SemanticGraph type without implying any
additional semantic subsystem implementation.
"""

from datashark_mcp.kernel.types import SemanticGraph

__all__ = ["SemanticGraph"]



