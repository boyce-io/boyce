# ADCIL canonical schema
# Authoritative semantic layer for DataShark

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

GRAPH_SCHEMA_VERSION = "0.1.0"


class NodeType(str, Enum):
    ENTITY = "entity"
    FIELD = "field"
    METRIC = "metric"
    TRANSFORMATION = "transformation"
    RELATIONSHIP = "relationship"  # logical relationship container, not an edge
    BUSINESS_CONCEPT = "business_concept"
    CONTEXT_TAG = "context_tag"
    DOCUMENT = "document"


class EdgeType(str, Enum):
    DEPENDS_ON = "depends_on"
    JOINS_TO = "joins_to"
    COMPUTES = "computes"
    DESCRIBES = "describes"
    OWNED_BY = "owned_by"
    DERIVED_FROM = "derived_from"


@dataclass(frozen=True)
class Provenance:
    system: str                     # e.g., "looker", "dbt", "airflow", "datahub"
    source_path: Optional[str] = None
    source_line: Optional[int] = None
    source_commit: Optional[str] = None
    extractor_version: Optional[str] = None
    # Optional extraction timestamp; when present, should be ISO 8601 in UTC.
    extracted_at: Optional[str] = None


def stable_node_id(system: str, node_type: NodeType, qualified_name: str, column: Optional[str] = None) -> str:
    parts = [system, node_type.value, qualified_name]
    if column:
        parts.append(column)
    return ":".join(parts)


def stable_edge_id(src_id: str, dst_id: str, edge_type: EdgeType) -> str:
    return f"edge:{src_id}->{dst_id}:{edge_type.value}"


def content_hash(payload: Dict[str, Any]) -> str:
    """sha256 of normalized JSON for change detection (keys sorted)."""
    norm = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


@dataclass
class Node:
    id: str
    type: NodeType
    system: str
    name: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    # Common semantic fields
    grain: Optional[str] = None                  # for Metric
    default_grain: Optional[str] = None          # for Entity/Explore
    dialect: Optional[str] = None                # for Entity (snowflake|bigquery|redshift|postgres|...)
    provenance: Provenance = field(default_factory=lambda: Provenance(system="unknown"))
    hash: Optional[str] = None                   # content-based hash (for incremental)


@dataclass
class Edge:
    id: str
    type: EdgeType
    src: str
    dst: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    provenance: Provenance = field(default_factory=lambda: Provenance(system="unknown"))
    hash: Optional[str] = None


@dataclass
class ValidationIssue:
    code: str
    message: str
    node_or_edge_id: Optional[str] = None
    provenance: Optional[Provenance] = None


@dataclass
class ValidationResult:
    ok: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    # Extended metadata for path/join validations
    path_depth: Optional[int] = None
    score: Optional[float] = None
    explanation: Optional[str] = None
    temporal_range: Optional[Dict[str, str]] = None


# Utility to compute node/edge hashes from stable subsets

def compute_node_hash(node: Node) -> str:
    payload = {
        "id": node.id,
        "type": node.type.value,
        "system": node.system,
        "name": node.name,
        "attributes": node.attributes,
        "grain": node.grain,
        "default_grain": node.default_grain,
        "dialect": node.dialect,
    }
    return content_hash(payload)


def compute_edge_hash(edge: Edge) -> str:
    payload = {
        "id": edge.id,
        "type": edge.type.value,
        "src": edge.src,
        "dst": edge.dst,
        "attributes": edge.attributes,
    }
    return content_hash(payload)
