"""
Security Validation

Validates that no PII or credentials appear in attributes or provenance.
"""

from __future__ import annotations

import re
from typing import List, Dict, Any
from datashark_mcp.context.models import Node, Edge


class SecurityValidationError(Exception):
    """Raised when PII or credentials are detected."""
    pass


# Common patterns for detecting secrets
SECRET_PATTERNS = [
    r"password\s*[:=]\s*['\"]?([^'\"]+)['\"]?",
    r"api[_-]?key\s*[:=]\s*['\"]?([^'\"]+)['\"]?",
    r"secret\s*[:=]\s*['\"]?([^'\"]+)['\"]?",
    r"token\s*[:=]\s*['\"]?([^'\"]+)['\"]?",
    r"credential\s*[:=]\s*['\"]?([^'\"]+)['\"]?",
    r"bearer\s+([a-zA-Z0-9_-]+)",
    r"sk_live_[a-zA-Z0-9]+",
    r"pk_live_[a-zA-Z0-9]+",
]

# Common patterns for detecting PII
PII_PATTERNS = [
    r"\b\d{3}-\d{2}-\d{4}\b",  # SSN
    r"\b\d{3}\.\d{2}\.\d{4}\b",  # SSN variant
    r"\b\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\b",  # Credit card
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # Email (if not redacted)
]

# Values that indicate redaction
REDACTED_INDICATORS = [
    "[REDACTED]",
    "[REDACTED]",
    "***",
    "sha256:",
    "hash:",
]


def is_redacted(value: str) -> bool:
    """Check if a value appears to be redacted."""
    value_lower = value.lower()
    return any(indicator.lower() in value_lower for indicator in REDACTED_INDICATORS)


def validate_no_secrets(text: str, context: str = "") -> List[str]:
    """
    Check for secrets in text.
    
    Args:
        text: Text to check
        context: Context string for error messages
        
    Returns:
        List of detected secret patterns (empty if none)
    """
    detected = []
    text_lower = text.lower()
    
    for pattern in SECRET_PATTERNS:
        matches = re.findall(pattern, text_lower, re.IGNORECASE)
        for match in matches:
            if match and not is_redacted(match):
                detected.append(f"Potential secret detected in {context}: {pattern}")
    
    return detected


def validate_no_pii(text: str, context: str = "") -> List[str]:
    """
    Check for PII in text.
    
    Args:
        text: Text to check
        context: Context string for error messages
        
    Returns:
        List of detected PII patterns (empty if none)
    """
    detected = []
    
    for pattern in PII_PATTERNS:
        matches = re.findall(pattern, text)
        for match in matches:
            if match and not is_redacted(match):
                detected.append(f"Potential PII detected in {context}: {pattern}")
    
    return detected


def validate_node_security(node: Node) -> None:
    """
    Validate node for security issues (no secrets or unredacted PII).
    
    Args:
        node: Node to validate
        
    Raises:
        SecurityValidationError if secrets or PII detected
    """
    issues = []
    
    # Check attributes
    attrs_str = str(node.attributes)
    issues.extend(validate_no_secrets(attrs_str, f"node {node.id} attributes"))
    issues.extend(validate_no_pii(attrs_str, f"node {node.id} attributes"))
    
    # Check provenance
    prov_str = f"{node.provenance.system} {node.provenance.source_path or ''}"
    issues.extend(validate_no_secrets(prov_str, f"node {node.id} provenance"))
    
    # Check name
    if node.name:
        issues.extend(validate_no_pii(node.name, f"node {node.id} name"))
    
    if issues:
        raise SecurityValidationError(f"Security issues detected: {'; '.join(issues)}")


def validate_edge_security(edge: Edge) -> None:
    """
    Validate edge for security issues.
    
    Args:
        edge: Edge to validate
        
    Raises:
        SecurityValidationError if secrets or PII detected
    """
    issues = []
    
    # Check attributes
    attrs_str = str(edge.attributes)
    issues.extend(validate_no_secrets(attrs_str, f"edge {edge.id} attributes"))
    issues.extend(validate_no_pii(attrs_str, f"edge {edge.id} attributes"))
    
    # Check provenance
    prov_str = f"{edge.provenance.system} {edge.provenance.source_path or ''}"
    issues.extend(validate_no_secrets(prov_str, f"edge {edge.id} provenance"))
    
    if issues:
        raise SecurityValidationError(f"Security issues detected: {'; '.join(issues)}")

