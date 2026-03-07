"""
DataShark Ingestion Engine

Production-grade file watching and context scanning for dbt, LookML, and SQL repositories.
"""

from datashark.ingestion.watcher import ProjectWatcher
from datashark.ingestion.sniper import ContextSniper

__all__ = ["ProjectWatcher", "ContextSniper"]
