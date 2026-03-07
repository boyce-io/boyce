"""
Parser registry — confidence-based dispatch for SnapshotParser plugins.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from boyce.types import SemanticSnapshot
from .base import SnapshotParser


class ParserRegistry:
    """Maintains a list of parsers and dispatches based on confidence."""

    def __init__(self) -> None:
        self._parsers: List[SnapshotParser] = []

    def register(self, parser: SnapshotParser) -> None:
        """Register a parser instance."""
        if not isinstance(parser, SnapshotParser):
            raise TypeError(f"{type(parser).__name__} does not implement SnapshotParser protocol")
        self._parsers.append(parser)

    def detect(self, path: Path) -> List[Tuple[SnapshotParser, float]]:
        """
        Return all parsers with confidence > 0, sorted descending by confidence.
        """
        results: List[Tuple[SnapshotParser, float]] = []
        for parser in self._parsers:
            confidence = parser.detect(path)
            if confidence > 0.0:
                results.append((parser, confidence))
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def parse(self, path: Path) -> SemanticSnapshot:
        """
        Detect the best parser for `path` and parse it.
        Tries parsers in confidence order. If the highest-confidence parser
        raises an exception, falls through to the next.
        """
        candidates = self.detect(path)
        if not candidates:
            raise ValueError(
                f"No parser can handle '{path}'. "
                f"Registered parsers: {[p.source_type() for p in self._parsers]}"
            )

        errors: List[Tuple[str, float, str]] = []
        for parser, confidence in candidates:
            try:
                return parser.parse(path)
            except Exception as e:
                errors.append((parser.source_type(), confidence, str(e)))

        error_details = "; ".join(
            f"{st} (conf={c:.1f}): {msg}" for st, c, msg in errors
        )
        raise ValueError(
            f"All parsers failed for '{path}'. Errors: {error_details}"
        )

    @property
    def registered_types(self) -> List[str]:
        """List source types of all registered parsers."""
        return [p.source_type() for p in self._parsers]


_default_registry: Optional[ParserRegistry] = None


def get_default_registry() -> ParserRegistry:
    """Get (or create) the default registry with all built-in parsers."""
    global _default_registry
    if _default_registry is None:
        _default_registry = ParserRegistry()
        from .dbt import DbtManifestParser, DbtProjectParser
        from .lookml import LookMLParser
        from .sqlite import SQLiteParser
        from .ddl import DDLParser
        from .tabular import CSVParser
        _default_registry.register(DbtManifestParser())
        _default_registry.register(DbtProjectParser())
        _default_registry.register(LookMLParser())
        _default_registry.register(SQLiteParser())
        _default_registry.register(DDLParser())
        _default_registry.register(CSVParser())
        try:
            from .tabular import ParquetParser, _PYARROW_AVAILABLE
            if _PYARROW_AVAILABLE:
                _default_registry.register(ParquetParser())
        except Exception:
            pass
        from .django import DjangoParser
        from .sqlalchemy_models import SQLAlchemyParser
        from .prisma import PrismaParser
        _default_registry.register(DjangoParser())
        _default_registry.register(SQLAlchemyParser())
        _default_registry.register(PrismaParser())
    return _default_registry


def reset_default_registry() -> None:
    """Reset the default registry. Useful for testing."""
    global _default_registry
    _default_registry = None
