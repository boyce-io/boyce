"""
Deterministic ID Utilities

Implements the deterministic ID algorithm from docs/ENTERPRISE_GRAPH_ARCHITECTURE.md.
All IDs are SHA-256 hashes of normalized preimage strings.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional


def _normalize(s: str) -> str:
    """
    Normalize string: trim, collapse whitespace, lowercase.
    
    Args:
        s: Input string
        
    Returns:
        Normalized string
    """
    if not s:
        return ""
    # Trim, lowercase, collapse whitespace
    return " ".join(s.strip().lower().split())


def normalize_json(obj: Dict[str, Any]) -> str:
    """
    Normalize JSON: stable key ordering, compact format.
    
    Args:
        obj: Dictionary to normalize
        
    Returns:
        Normalized JSON string (sorted keys, compact format)
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def compute_node_id(
    type: str,
    system: str,
    repo: Optional[str],
    schema: Optional[str],
    name: str,
    attributes: Optional[Dict[str, Any]] = None
) -> str:
    """
    Compute deterministic node ID using SHA-256 of normalized preimage.
    
    Preimage format: type|system|repo|schema|name
    - Normalize all components: lowercase, trim, collapse whitespace
    - Replace None with empty string
    - Compute SHA256 of lowercase(preimage)
    - Return hex digest (64 chars)
    
    Args:
        type: Node type (e.g., "ENTITY", "METRIC")
        system: Source system identifier
        repo: Repository identifier (or None)
        schema: Schema/namespace identifier (or None)
        name: Entity name
        attributes: Optional attributes dict (currently not used in ID computation)
        
    Returns:
        SHA-256 hex digest (64 characters)
    """
    # Normalize all components
    normalized = [
        _normalize(type),
        _normalize(system),
        _normalize(repo or ""),
        _normalize(schema or ""),
        _normalize(name),
    ]
    
    # Join with pipe separator
    preimage = "|".join(normalized)
    
    # Compute SHA256 of lowercase preimage
    sha256_hash = hashlib.sha256(preimage.lower().encode("utf-8"))
    
    # Return hex digest
    return sha256_hash.hexdigest()


def compute_edge_id(
    type: str,
    src_id: str,
    dst_id: str,
    join_signature: Optional[Dict[str, Any]] = None
) -> str:
    """
    Compute deterministic edge ID using SHA-256 of normalized preimage.
    
    Preimage format: type|src_id|dst_id|join_signature
    - Normalize edge type: lowercase, trim
    - Use normalized src_id and dst_id (already deterministic)
    - Include join_signature if present (normalized JSON with stable key ordering)
    - Compute SHA256 of lowercase(preimage)
    - Return hex digest (64 chars)
    
    Args:
        type: Edge type (e.g., "JOINS_TO", "DERIVES_FROM")
        src_id: Source node ID (already deterministic)
        dst_id: Destination node ID (already deterministic)
        join_signature: Optional join signature dict (normalized as JSON)
        
    Returns:
        SHA-256 hex digest (64 characters)
    """
    # Normalize edge type
    normalized_type = _normalize(type)
    
    # Normalize join signature if present
    if join_signature:
        normalized_sig = normalize_json(join_signature)
    else:
        normalized_sig = ""
    
    # Build preimage
    preimage = f"{normalized_type}|{src_id}|{dst_id}|{normalized_sig}"
    
    # Compute SHA256 of lowercase preimage
    sha256_hash = hashlib.sha256(preimage.lower().encode("utf-8"))
    
    # Return hex digest
    return sha256_hash.hexdigest()

