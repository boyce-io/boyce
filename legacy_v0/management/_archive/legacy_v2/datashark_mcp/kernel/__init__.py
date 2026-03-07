"""DataShark Safety Kernel Module.

This module provides the trusted governance layer for the DataShark Engine,
enforcing security boundaries between trusted and untrusted components.
"""

from datashark_mcp.kernel.exceptions import (
    ContextValidationError,
    DataSharkKernelError,
    GovernanceViolationError,
    PolicyNotFoundException,
    SnapshotIntegrityError,
    SnapshotNotFoundError,
)
from datashark_mcp.kernel.snapshot_store import SnapshotStore
from datashark_mcp.kernel.snapshot_factory import SnapshotFactory

__all__ = [
    "DataSharkKernelError",
    "GovernanceViolationError",
    "PolicyNotFoundException",
    "SnapshotIntegrityError",
    "SnapshotNotFoundError",
    "ContextValidationError",
    "SnapshotStore",
    "SnapshotFactory",
]

