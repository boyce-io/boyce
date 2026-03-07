"""
Determinism Utilities

Provides functions for normalizing timestamps and generating deterministic IDs
to ensure reproducible outputs across pipeline runs.
"""
import hashlib
import json
from typing import Any, Dict, Optional


def normalize_timestamp(ts: Optional[str], content: Optional[str] = None) -> str:
    """
    Return a reproducible pseudo-timestamp based solely on content.
    
    If content is provided, use it to derive the timestamp.
    Otherwise, use the timestamp string itself as the content.
    
    Args:
        ts: Original timestamp string (ISO 8601 format)
        content: Optional content string to use for normalization
        
    Returns:
        Normalized timestamp string in ISO 8601 format
    """
    if not ts:
        return "1970-01-01T00:00:00Z"
    
    # Use content if provided, otherwise use timestamp itself
    source = content if content is not None else ts
    
    # Derive pseudo-time from stable hash of content
    h = hashlib.sha1(source.encode()).hexdigest()
    # Use hash to create deterministic time components
    hour = int(h[:2], 16) % 24
    minute = int(h[2:4], 16) % 60
    second = int(h[4:6], 16) % 60
    return f"1970-01-01T{hour:02d}:{minute:02d}:{second:02d}Z"


def normalize_provenance_for_hash(provenance: Dict[str, Any], node_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Normalize provenance dictionary for deterministic hashing.
    
    Replaces timestamp fields with normalized versions based on content.
    
    Args:
        provenance: Provenance dictionary
        node_id: Optional node ID to use as content for normalization
        
    Returns:
        Normalized provenance dictionary
    """
    normalized = provenance.copy()
    
    # Normalize extracted_at using node_id as content if available
    if "extracted_at" in normalized:
        content = node_id if node_id else f"{provenance.get('system', '')}:{provenance.get('source_path', '')}"
        normalized["extracted_at"] = normalize_timestamp(normalized["extracted_at"], content=content)
    
    # Normalize other timestamp fields if present
    for field in ["created_at", "updated_at", "created_ts", "updated_ts"]:
        if field in normalized:
            content = node_id if node_id else f"{provenance.get('system', '')}:{field}"
            normalized[field] = normalize_timestamp(normalized[field], content=content)
    
    return normalized


def deterministic_trace_id(trace_content: Dict[str, Any]) -> str:
    """
    Generate deterministic trace ID from trace content.
    
    Args:
        trace_content: Dictionary containing trace information
        
    Returns:
        Deterministic trace ID (16 hex characters)
    """
    # Create normalized payload (exclude volatile fields)
    normalized = trace_content.copy()
    
    # Remove or normalize timestamp fields
    for field in ["trace_start_time", "timestamp", "latency_ms"]:
        if field in normalized:
            del normalized[field]
    
    # Sort keys and serialize
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(payload.encode()).hexdigest()[:16]


def normalize_dict_for_hash(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a dictionary for deterministic hashing by:
    - Sorting keys alphabetically
    - Normalizing timestamps in provenance
    - Rounding numeric values to fixed precision
    
    Args:
        data: Dictionary to normalize
        
    Returns:
        Normalized dictionary with sorted keys
    """
    normalized = {}
    
    # Sort keys alphabetically
    for key in sorted(data.keys()):
        value = data[key]
        
        # Handle nested dictionaries
        if isinstance(value, dict):
            if key == "provenance":
                # Normalize provenance with node_id if available
                node_id = data.get("id") if isinstance(data, dict) else None
                normalized[key] = normalize_provenance_for_hash(value, node_id)
            else:
                normalized[key] = normalize_dict_for_hash(value)
        # Handle lists - normalize each item
        elif isinstance(value, list):
            normalized[key] = [
                normalize_dict_for_hash(item) if isinstance(item, dict) else item
                for item in value
            ]
        # Round floats to 2 decimal places for stability
        elif isinstance(value, float):
            normalized[key] = round(value, 2)
        else:
            normalized[key] = value
    
    return normalized

