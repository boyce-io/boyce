from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import json
from jsonschema import Draft202012Validator, ValidationError as SchemaValidationError

from datashark_mcp.context.schema_loader import load_graph_schema, load_manifest_schema


@dataclass
class SnapshotValidationResult:
    snapshot_path: Path
    nodes_valid: bool
    edges_valid: bool
    manifest_valid: bool
    errors: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.nodes_valid and self.edges_valid and self.manifest_valid


def _get_node_and_edge_schemas() -> Dict[str, Dict[str, Any]]:
    """
    Extract Node and Edge schemas (with definitions) from graph_schema.json.
    """
    full_schema = load_graph_schema()
    node_schema: Dict[str, Any] | None = None
    edge_schema: Dict[str, Any] | None = None

    for item in full_schema.get("oneOf", []):
        title = item.get("title")
        if title == "Node":
            node_schema = {
                **item,
                "definitions": full_schema.get("definitions", {}),
            }
        elif title == "Edge":
            edge_schema = {
                **item,
                "definitions": full_schema.get("definitions", {}),
            }

    if node_schema is None or edge_schema is None:
        raise ValueError("Node and/or Edge schema not found in graph_schema.json oneOf")

    return {"node": node_schema, "edge": edge_schema, "full": full_schema}


def validate_snapshot_dir(path: Path) -> SnapshotValidationResult:
    """
    Validate nodes.json, edges.json, and manifest.json in a snapshot directory
    against graph_schema.json and manifest_schema.json.
    """
    snapshot_path = Path(path)
    result = SnapshotValidationResult(
        snapshot_path=snapshot_path,
        nodes_valid=True,
        edges_valid=True,
        manifest_valid=True,
    )

    nodes_file = snapshot_path / "nodes.json"
    edges_file = snapshot_path / "edges.json"
    manifest_file = snapshot_path / "manifest.json"

    try:
        with nodes_file.open("r", encoding="utf-8") as f:
            nodes = json.load(f)
    except Exception as e:
        result.nodes_valid = False
        result.errors.append(f"Failed to read nodes.json: {e}")
        nodes = []

    try:
        with edges_file.open("r", encoding="utf-8") as f:
            edges = json.load(f)
    except Exception as e:
        result.edges_valid = False
        result.errors.append(f"Failed to read edges.json: {e}")
        edges = []

    try:
        with manifest_file.open("r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        result.manifest_valid = False
        result.errors.append(f"Failed to read manifest.json: {e}")
        manifest = {}

    # Graph schema validation
    try:
        schemas = _get_node_and_edge_schemas()
        node_schema = schemas["node"]
        edge_schema = schemas["edge"]
        full_schema = schemas["full"]

        # Use Draft202012Validator with registry for $ref resolution
        from referencing import Registry
        from referencing.jsonschema import DRAFT202012

        registry = Registry().with_resource("https://datashark/schema", full_schema)

        node_validator = Draft202012Validator(node_schema, registry=registry)
        edge_validator = Draft202012Validator(edge_schema, registry=registry)

        for n in nodes:
            try:
                node_validator.validate(n)
            except SchemaValidationError as e:
                result.nodes_valid = False
                result.errors.append(f"Node schema validation failed: {e.message}")
                break

        for e in edges:
            try:
                edge_validator.validate(e)
            except SchemaValidationError as e:
                result.edges_valid = False
                result.errors.append(f"Edge schema validation failed: {e.message}")
                break
    except Exception as e:
        result.nodes_valid = False
        result.edges_valid = False
        result.errors.append(f"Graph schema validation error: {e}")

    # Manifest schema validation
    try:
        manifest_schema = load_manifest_schema()
        manifest_validator = Draft202012Validator(manifest_schema)
        manifest_validator.validate(manifest)
    except SchemaValidationError as e:
        result.manifest_valid = False
        result.errors.append(f"Manifest schema validation failed: {e.message}")
    except Exception as e:
        result.manifest_valid = False
        result.errors.append(f"Manifest schema validation error: {e}")

    return result


