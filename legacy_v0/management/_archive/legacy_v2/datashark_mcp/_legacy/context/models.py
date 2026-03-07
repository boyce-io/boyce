"""
Enterprise Graph Models

Defines Node and Edge dataclasses matching docs/graph_schema.json exactly.
Includes validation and serialization methods.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, Optional
from jsonschema import Draft202012Validator, ValidationError as SchemaValidationError
from referencing import Registry
from pathlib import Path
from datashark_mcp.context.schema_loader import load_graph_schema, get_schema_root
from datashark_mcp.context.determinism import normalize_provenance_for_hash


class GraphValidationError(Exception):
    """Raised when node/edge fails schema validation."""
    pass


# Cache for schema and registry (module-level cache)
_graph_schema_cache: Optional[Dict[str, Any]] = None
_graph_registry_cache: Optional[Registry] = None


def _load_graph_schema_with_registry() -> tuple[Dict[str, Any], Registry]:
    """
    Load graph_schema.json with Registry for $ref resolution.
    Uses caching to prevent repeated I/O during validation loops.
    """
    global _graph_schema_cache, _graph_registry_cache
    
    if _graph_schema_cache is None or _graph_registry_cache is None:
        schema = load_graph_schema()
        # Create registry with schema resource
        registry = Registry().with_resource("https://datashark/schema", schema)
        _graph_schema_cache = schema
        _graph_registry_cache = registry
    
    return _graph_schema_cache, _graph_registry_cache


def _load_graph_schema() -> Dict[str, Any]:
    """Load graph_schema.json using robust schema loader."""
    schema, _ = _load_graph_schema_with_registry()
    return schema


@dataclass
class Provenance:
    """Provenance information for nodes and edges."""
    system: str
    source_path: str
    extractor_version: str
    extracted_at: str  # ISO 8601 format
    source_commit: Optional[str] = None

    def to_dict(self, normalize_timestamps: bool = False, node_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Convert to dict preserving key order.
        
        Args:
            normalize_timestamps: If True, normalize timestamps for deterministic hashing
            node_id: Optional node ID to use for timestamp normalization
        """
        result = {
            "system": self.system,
            "source_path": self.source_path,
            "extractor_version": self.extractor_version,
            "extracted_at": self.extracted_at,
        }
        if self.source_commit is not None:
            result["source_commit"] = self.source_commit
        
        # Normalize timestamps if requested (for deterministic hashing)
        if normalize_timestamps:
            result = normalize_provenance_for_hash(result, node_id)
        
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Provenance:
        """Create Provenance from dict."""
        return cls(
            system=data["system"],
            source_path=data["source_path"],
            extractor_version=data["extractor_version"],
            extracted_at=data["extracted_at"],
            source_commit=data.get("source_commit"),
        )


@dataclass
class Node:
    """Node in the unified graph, matching graph_schema.json."""
    id: str
    system: str
    type: str  # ENTITY, FIELD, METRIC, TRANSFORMATION, BUSINESS_CONCEPT, etc.
    name: str
    attributes: Dict[str, Any]
    provenance: Provenance
    repo: Optional[str] = None
    schema: Optional[str] = None
    deleted_at: Optional[str] = None  # ISO 8601 format if tombstoned

    def to_dict(self, normalize_timestamps: bool = False) -> Dict[str, Any]:
        """
        Convert to dict matching graph_schema.json, preserving key order.
        
        Args:
            normalize_timestamps: If True, normalize timestamps for deterministic hashing
        """
        result = {
            "id": self.id,
            "system": self.system,
            "type": self.type,
            "name": self.name,
            "attributes": self.attributes,
            "provenance": self.provenance.to_dict(normalize_timestamps=normalize_timestamps, node_id=self.id),
        }
        if self.repo is not None:
            result["repo"] = self.repo
        if self.schema is not None:
            result["schema"] = self.schema
        if self.deleted_at is not None:
            result["deleted_at"] = self.deleted_at
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Node:
        """Create Node from dict."""
        return cls(
            id=data["id"],
            system=data["system"],
            type=data["type"],
            name=data["name"],
            attributes=data["attributes"],
            provenance=Provenance.from_dict(data["provenance"]),
            repo=data.get("repo"),
            schema=data.get("schema"),
            deleted_at=data.get("deleted_at"),
        )

    def validate(self) -> None:
        """Validate node against graph_schema.json. Raises GraphValidationError on failure."""
        full_schema, registry = _load_graph_schema_with_registry()
        # Find Node schema in oneOf
        node_schema = None
        for item in full_schema.get("oneOf", []):
            if item.get("title") == "Node":
                # Include definitions for $ref resolution
                node_schema = {
                    **item,
                    "$schema": full_schema.get("$schema"),
                    "definitions": full_schema.get("definitions", {})
                }
                break
        
        if not node_schema:
            raise GraphValidationError("Node schema not found in graph_schema.json")
        
        try:
            # Use Draft202012Validator with registry
            validator = Draft202012Validator(node_schema, registry=registry)
            validator.validate(self.to_dict())
        except SchemaValidationError as e:
            raise GraphValidationError(f"Node validation failed: {e.message}") from e


@dataclass
class Edge:
    """Edge in the unified graph, matching graph_schema.json."""
    id: str
    src: str
    dst: str
    type: str  # Must be one of: JOINS_TO, DERIVES_FROM, DEPENDS_ON, DESCRIBES
    attributes: Dict[str, Any]
    provenance: Provenance
    deleted_at: Optional[str] = None  # ISO 8601 format if tombstoned

    def to_dict(self, normalize_timestamps: bool = False) -> Dict[str, Any]:
        """
        Convert to dict matching graph_schema.json, preserving key order.
        
        Args:
            normalize_timestamps: If True, normalize timestamps for deterministic hashing
        """
        result = {
            "id": self.id,
            "src": self.src,
            "dst": self.dst,
            "type": self.type,
            "attributes": self.attributes,
            "provenance": self.provenance.to_dict(normalize_timestamps=normalize_timestamps, node_id=self.id),
        }
        if self.deleted_at is not None:
            result["deleted_at"] = self.deleted_at
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Edge:
        """Create Edge from dict."""
        return cls(
            id=data["id"],
            src=data["src"],
            dst=data["dst"],
            type=data["type"],
            attributes=data["attributes"],
            provenance=Provenance.from_dict(data["provenance"]),
            deleted_at=data.get("deleted_at"),
        )

    def validate(self) -> None:
        """Validate edge against graph_schema.json. Raises GraphValidationError on failure."""
        full_schema, registry = _load_graph_schema_with_registry()
        # Find Edge schema in oneOf
        edge_schema = None
        for item in full_schema.get("oneOf", []):
            if item.get("title") == "Edge":
                # Include definitions for $ref resolution
                edge_schema = {
                    **item,
                    "$schema": full_schema.get("$schema"),
                    "definitions": full_schema.get("definitions", {})
                }
                break
        
        if not edge_schema:
            raise GraphValidationError("Edge schema not found in graph_schema.json")
        
        # Validate edge type enum
        valid_types = ["JOINS_TO", "DERIVES_FROM", "DEPENDS_ON", "DESCRIBES"]
        if self.type not in valid_types:
            raise GraphValidationError(f"Invalid edge type: {self.type}. Must be one of {valid_types}")
        
        try:
            # Use Draft202012Validator with registry
            validator = Draft202012Validator(edge_schema, registry=registry)
            validator.validate(self.to_dict())
        except SchemaValidationError as e:
            raise GraphValidationError(f"Edge validation failed: {e.message}") from e

