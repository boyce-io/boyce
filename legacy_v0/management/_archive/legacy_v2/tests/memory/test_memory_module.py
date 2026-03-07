"""
Placeholder tests for the memory module interfaces.

These tests ensure that the MemorySubsystem contract is present.
"""

from datashark_mcp.memory import MemorySubsystem


def test_memory_subsystem_interface_exists() -> None:
    """MemorySubsystem should be importable and instantiable as a stub."""
    memory = MemorySubsystem()
    assert memory is not None


