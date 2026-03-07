"""
Placeholder tests for the semantic module interfaces.

These tests assert that the SemanticGraph interface exists and can be imported.
No business logic is exercised at this stage.
"""

from datashark_mcp.semantic import SemanticGraph


def test_semantic_graph_interface_exists() -> None:
    """SemanticGraph should be importable and instantiable as a stub."""
    graph = SemanticGraph()
    assert graph is not None


