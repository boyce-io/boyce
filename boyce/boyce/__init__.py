"""
Boyce — Semantic protocol and safety layer for agentic database workflows.

Named for Raymond F. Boyce, co-inventor of SQL (1974) and co-author of
Boyce-Codd Normal Form (BCNF).
"""

__version__ = "0.1.0"

from boyce.kernel import process_request
from boyce.types import SemanticSnapshot, Entity, FieldDef, JoinDef
from boyce.safety import lint_redshift_compat
from boyce.graph import SemanticGraph

__all__ = [
    # Key symbols — importable directly from `boyce`
    "process_request",
    "SemanticSnapshot",
    "Entity",
    "FieldDef",
    "JoinDef",
    "lint_redshift_compat",
    "SemanticGraph",
    # Modules
    "types",
    "validation",
    "graph",
    "safety",
    "store",
    "kernel",
    "server",
]
