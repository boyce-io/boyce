"""
DataShark Instance Management

Manages multiple DataShark instances with isolated configurations,
manifests, caches, and logs.
"""

__version__ = "0.2.0"

from .manager import InstanceManager
from .registry import InstanceRegistry
from .migrate import MigrationManager

__all__ = ["InstanceManager", "InstanceRegistry", "MigrationManager"]

