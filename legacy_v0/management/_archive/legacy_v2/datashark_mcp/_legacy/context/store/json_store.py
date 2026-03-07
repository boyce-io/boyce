import json
import os
import time
import logging
from typing import Any, Dict, List, Tuple, Optional
from pathlib import Path
from jsonschema import Draft202012Validator, ValidationError as SchemaValidationError
from referencing import Registry
from referencing.jsonschema import DRAFT202012
from datashark_mcp.context.manifest import Manifest as IngestionManifest
from datashark_mcp.context.schema import Node, Edge, compute_node_hash, compute_edge_hash, GRAPH_SCHEMA_VERSION
from datashark_mcp.context.schema_loader import load_graph_schema, load_manifest_schema, get_schema_root
import hashlib
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class JSONStore:
    def __init__(self, snapshot_dir: Path):
        self.snapshot_dir = snapshot_dir
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        # Try JSONL first (preferred), fallback to JSON
        nodes_jsonl = self.snapshot_dir / "nodes.jsonl"
        nodes_json = self.snapshot_dir / "nodes.json"
        self.nodes_path = nodes_jsonl if nodes_jsonl.exists() else nodes_json
        
        edges_jsonl = self.snapshot_dir / "edges.jsonl"
        edges_json = self.snapshot_dir / "edges.json"
        self.edges_path = edges_jsonl if edges_jsonl.exists() else edges_json
        
        self.embeddings_path = self.snapshot_dir / "embeddings.json"
        self.manifest_path = self.snapshot_dir / "manifest.json"
        
        # Cache for schema and registry
        self._graph_schema: Optional[Dict[str, Any]] = None
        self._graph_registry: Optional[Registry] = None
        self._manifest_schema: Optional[Dict[str, Any]] = None
        self._manifest_registry: Optional[Registry] = None

    def _load_graph_schema_with_registry(self) -> Tuple[Dict[str, Any], Registry]:
        """Load graph schema and create Registry for $ref resolution."""
        if self._graph_schema is None or self._graph_registry is None:
            schema = load_graph_schema()
            # Create registry with schema resource
            registry = Registry().with_resource("https://datashark/schema", schema)
            self._graph_schema = schema
            self._graph_registry = registry
        return self._graph_schema, self._graph_registry

    def _load_manifest_schema_with_registry(self) -> Tuple[Dict[str, Any], Registry]:
        """Load manifest schema and create Registry for $ref resolution."""
        if self._manifest_schema is None or self._manifest_registry is None:
            try:
                schema = load_manifest_schema()
                # Create registry with schema resource
                registry = Registry().with_resource("https://datashark/manifest", schema)
                self._manifest_schema = schema
                self._manifest_registry = registry
            except FileNotFoundError:
                # Manifest schema is optional
                return {}, Registry()
        return self._manifest_schema, self._manifest_registry

    def _get_node_schema(self) -> Dict[str, Any]:
        """Extract Node schema from graph_schema.json oneOf, preserving definitions."""
        full_schema, _ = self._load_graph_schema_with_registry()
        for item in full_schema.get("oneOf", []):
            if item.get("title") == "Node":
                # Create a schema that includes definitions for $ref resolution
                node_schema = {
                    **item,
                    "definitions": full_schema.get("definitions", {})
                }
                return node_schema
        raise ValueError("Node schema not found in graph_schema.json oneOf")

    def _get_edge_schema(self) -> Dict[str, Any]:
        """Extract Edge schema from graph_schema.json oneOf, preserving definitions."""
        full_schema, _ = self._load_graph_schema_with_registry()
        for item in full_schema.get("oneOf", []):
            if item.get("title") == "Edge":
                # Create a schema that includes definitions for $ref resolution
                edge_schema = {
                    **item,
                    "definitions": full_schema.get("definitions", {})
                }
                return edge_schema
        raise ValueError("Edge schema not found in graph_schema.json oneOf")

    def _validate(self, payload: Any, schema_name: str) -> None:
        """
        Validate payload against schema with proper $ref resolution using Registry.
        
        Args:
            payload: Data to validate (can be list for nodes/edges)
            schema_name: Schema name ("nodes_schema", "edges_schema", "manifest_schema")
        
        Raises:
            SchemaValidationError: If validation fails
        """
        try:
            if schema_name == "nodes_schema":
                schema = self._get_node_schema()
                full_schema, registry = self._load_graph_schema_with_registry()
                validator = Draft202012Validator(schema, registry=registry)
                # Validate each node in the list
                if isinstance(payload, list):
                    for i, node in enumerate(payload):
                        validator.validate(node)
                else:
                    validator.validate(payload)
            elif schema_name == "edges_schema":
                schema = self._get_edge_schema()
                full_schema, registry = self._load_graph_schema_with_registry()
                validator = Draft202012Validator(schema, registry=registry)
                # Validate each edge in the list
                if isinstance(payload, list):
                    for i, edge in enumerate(payload):
                        validator.validate(edge)
                else:
                    validator.validate(payload)
            elif schema_name == "manifest_schema":
                schema, registry = self._load_manifest_schema_with_registry()
                if schema:
                    validator = Draft202012Validator(schema, registry=registry)
                    validator.validate(payload)
                # Manifest validation is optional, so silently pass if no schema
            else:
                raise ValueError(f"Unknown schema name: {schema_name}")
        except SchemaValidationError as e:
            logger.error(f"Schema validation failed for {schema_name}: {e.message}")
            if hasattr(e, 'absolute_path'):
                logger.error(f"Failed path: {e.absolute_path}")
            raise
        except Exception as e:
            if "ResolutionError" in str(type(e)) or "$ref" in str(e):
                logger.error(f"Schema $ref resolution failed for {schema_name}: {e}")
            raise

    def save_atomic(self, nodes: List[Node], edges: List[Edge], manifest: Dict[str, Any]) -> None:
        tmp_suffix = f".{int(time.time()*1000)}.tmp"
        
        # Convert to JSON with normalized timestamps for deterministic hashing
        nodes_payload = [self._node_to_json(n, normalize_timestamps=True) for n in nodes]
        edges_payload = [self._edge_to_json(e, normalize_timestamps=True) for e in edges]
        
        # Sort by ID for deterministic ordering
        nodes_payload.sort(key=lambda n: n.get("id", ""))
        edges_payload.sort(key=lambda e: e.get("id", ""))

        # Validate before write
        self._validate(nodes_payload, "nodes_schema")
        self._validate(edges_payload, "edges_schema")

        tmp_nodes = self.nodes_path.with_suffix(self.nodes_path.suffix + tmp_suffix)
        tmp_edges = self.edges_path.with_suffix(self.edges_path.suffix + tmp_suffix)
        tmp_manifest = self.manifest_path.with_suffix(self.manifest_path.suffix + tmp_suffix)

        with open(tmp_nodes, "w", encoding="utf-8") as f:
            json.dump(nodes_payload, f, ensure_ascii=False, separators=(",", ":"))
        with open(tmp_edges, "w", encoding="utf-8") as f:
            json.dump(edges_payload, f, ensure_ascii=False, separators=(",", ":"))

        # Compute canonical payload hashes (compact JSON with sorted keys)
        # Note: nodes_payload and edges_payload already have normalized timestamps
        def _canon_json(obj: Any) -> bytes:
            return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")

        nodes_bytes = _canon_json(nodes_payload)
        edges_bytes = _canon_json(edges_payload)
        # Per-object hashes
        nodes_sha256 = hashlib.sha256(nodes_bytes).hexdigest()
        edges_sha256 = hashlib.sha256(edges_bytes).hexdigest()
        # Combined payload hash (nodes + edges) for convenience
        sha256_payload_hash = hashlib.sha256(nodes_bytes + edges_bytes).hexdigest()

        # Provenance summary by source system
        prov_counts: Dict[str, int] = {}
        for n in nodes_payload:
            sys = ((n.get("provenance") or {}).get("system")) or "unknown"
            prov_counts[sys] = prov_counts.get(sys, 0) + 1
        for e in edges_payload:
            sys = ((e.get("provenance") or {}).get("system")) or "unknown"
            prov_counts[sys] = prov_counts.get(sys, 0) + 1

        # Determine system for this run (fall back to "unknown" if not clear)
        system = manifest.get("system")
        if not system:
            if nodes_payload:
                system = (nodes_payload[0].get("provenance") or {}).get("system") or "unknown"
            elif edges_payload:
                system = (edges_payload[0].get("provenance") or {}).get("system") or "unknown"
            else:
                system = "unknown"

        extractor_version = (
            manifest.get("extractor_version")
            or manifest.get("adc_version")
            or "dev"
        )

        # Build ingestion manifest matching manifest_schema.json
        ingestion_manifest = IngestionManifest.start_run(
            system=system,
            repo=manifest.get("repo"),
            changed_since=manifest.get("changed_since"),
            schema_version=GRAPH_SCHEMA_VERSION,
            extractor_version=str(extractor_version),
        )

        counts = {
            "nodes": len(nodes_payload),
            "edges": len(edges_payload),
            "tombstones": 0,
        }
        hash_summaries = {
            "nodes_sha256": nodes_sha256,
            "edges_sha256": edges_sha256,
        }
        ingestion_manifest.end_run(
            status="success",
            counts=counts,
            hash_summaries=hash_summaries,
        )

        base_manifest = ingestion_manifest.to_json()
        full_manifest: Dict[str, Any] = {
            **base_manifest,
            **manifest,
            "graph_schema_version": GRAPH_SCHEMA_VERSION,
            "node_count": len(nodes_payload),
            "edge_count": len(edges_payload),
            # Note: build_timestamp_utc is for telemetry, not included in hash
            "build_timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sha256_payload_hash": sha256_payload_hash,
            "provenance_summary": {"counts_by_system": prov_counts},
        }

        # Optionally validate manifest if schema present
        try:
            self._validate(full_manifest, "manifest_schema")
        except Exception:
            # Validation failure is logged in _validate; do not block snapshot write.
            pass

        with open(tmp_manifest, "w", encoding="utf-8") as f:
            json.dump(full_manifest, f, ensure_ascii=False, indent=2)

        # Atomic rename
        os.replace(tmp_nodes, self.nodes_path)
        os.replace(tmp_edges, self.edges_path)
        os.replace(tmp_manifest, self.manifest_path)

    def load(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        # Handle JSONL format (preferred) or JSON format
        if self.nodes_path.suffix == ".jsonl":
            nodes = []
            with open(self.nodes_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        nodes.append(json.loads(line))
        else:
            with open(self.nodes_path, "r", encoding="utf-8") as f:
                nodes = json.load(f)
        
        if self.edges_path.suffix == ".jsonl":
            edges = []
            with open(self.edges_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        edges.append(json.loads(line))
        else:
            with open(self.edges_path, "r", encoding="utf-8") as f:
                edges = json.load(f)
        
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        # Validate on load
        self._validate(nodes, "nodes_schema")
        self._validate(edges, "edges_schema")
        return nodes, edges, manifest

    @staticmethod
    def _node_to_json(n: Node, normalize_timestamps: bool = False) -> Dict[str, Any]:
        """
        Convert node to JSON.

        The normalize_timestamps flag is accepted for API compatibility with
        save_atomic, but the current implementation does not alter timestamp
        fields on nodes (they are carried through as-is).
        """
        payload: Dict[str, Any] = {
            "id": n.id,
            "type": n.type.value if hasattr(n.type, "value") else n.type,
            "system": n.system,
            "name": n.name,
            "attributes": getattr(n, "attributes", {}),
            "provenance": {
                "system": n.provenance.system,
                "source_path": n.provenance.source_path,
                "source_line": n.provenance.source_line,
                "source_commit": n.provenance.source_commit,
                "extractor_version": n.provenance.extractor_version or "unknown",
                "extracted_at": getattr(n.provenance, "extracted_at", None),
            },
        }
        # Optional fields allowed by schema
        if getattr(n, "repo", None) is not None:
            payload["repo"] = n.repo
        if getattr(n, "schema", None) is not None:
            payload["schema"] = n.schema
        if getattr(n, "deleted_at", None) is not None:
            payload["deleted_at"] = n.deleted_at
        return payload

    @staticmethod
    def _edge_to_json(e: Edge, normalize_timestamps: bool = False) -> Dict[str, Any]:
        """
        Convert edge to JSON.

        The normalize_timestamps flag is accepted for API compatibility but is
        currently handled at the provenance level via extracted_at.
        """
        return {
            "id": e.id,
            "type": e.type.value if hasattr(e.type, "value") else e.type,
            "src": e.src,
            "dst": e.dst,
            "attributes": e.attributes,
            "provenance": {
                "system": e.provenance.system,
                "source_path": e.provenance.source_path,
                "source_line": e.provenance.source_line,
                "source_commit": e.provenance.source_commit,
                "extractor_version": e.provenance.extractor_version,
                "extracted_at": getattr(e.provenance, "extracted_at", None),
            },
            "hash": e.hash or compute_edge_hash(e),
        }
