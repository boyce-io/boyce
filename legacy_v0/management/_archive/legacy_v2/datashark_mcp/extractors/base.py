from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional
from abc import ABC, abstractmethod


@dataclass(frozen=True)
class RawArtifact:
    """
    Raw artifact emitted by extractors (native schema, no normalization).

    Fields:
      - type: "entity" | "field" | "metric" | "relationship" | "transformation" | "document" | "glossary" | ...
      - name: canonical/native identifier
      - system: "looker" | "dbt" | "airflow" | "datahub" | "warehouse" | ...
      - sql: optional native SQL expression (for metrics/transforms)
      - dependencies: list of dependent native identifiers
      - attributes: arbitrary native fields (label, aggregation, enums, etc.)
      - source_path: repo path/file where extracted
      - source_line: optional line number
      - source_commit: repo commit hash (if available)
      - extractor_version: version string of the extractor
      - hash: stable content hash computed by extractor for change detection
    """
    type: str
    name: str
    system: str
    sql: Optional[str]
    dependencies: List[str]
    attributes: Dict[str, Any]
    source_path: Optional[str]
    source_line: Optional[int]
    source_commit: Optional[str]
    extractor_version: Optional[str]
    hash: str


@dataclass(frozen=True)
class HealthReport:
    ok: bool
    message: str
    coverage: Optional[Dict[str, Any]] = None


class Extractor(ABC):
    @abstractmethod
    def ingest(self, config: Dict[str, Any]) -> Iterator[RawArtifact]:
        """
        Yield RawArtifact records from the source.
        Extractors must be stateless and must not normalize or persist.
        """
        raise NotImplementedError

    @abstractmethod
    def incremental_ingest(self, config: Dict[str, Any], since: Optional[str]) -> Iterator[RawArtifact]:
        """
        Yield only changed RawArtifacts since given commit/point in time.
        """
        raise NotImplementedError

    @abstractmethod
    def health_check(self, config: Dict[str, Any]) -> HealthReport:
        """
        Return source availability and coverage summary.
        """
        raise NotImplementedError
