"""
Placeholder tests for the executor module interfaces.

These tests verify that the ExecutionLoop and ExecutionResult contracts exist.
"""

from datashark_mcp.executor import ExecutionLoop, ExecutionResult


def test_executor_interfaces_exist() -> None:
    """ExecutionLoop and ExecutionResult should be importable stubs."""
    loop = ExecutionLoop()
    result = ExecutionResult(success=False, payload=None, error={})
    assert loop is not None
    assert result.success is False


