"""Safety Kernel Type Definitions.

This module defines the core immutable types used by the Safety Kernel
for governance, including UserContext, SnapshotID, SemanticGraph, and ProjectedGraph.
"""

import re
from typing import List

from pydantic import BaseModel, Field, field_validator


class UserContext(BaseModel):
    """Immutable user context for governance and access control.
    
    This model represents the authenticated user's identity and roles,
    which are used by the Safety Kernel to enforce access policies.
    
    Attributes:
        user_id: Unique identifier for the user
        roles: List of role identifiers assigned to the user
        tenant_id: Identifier for the tenant/organization the user belongs to
    """
    
    model_config = {"frozen": True}
    
    user_id: str
    roles: List[str]
    tenant_id: str


class SnapshotID(BaseModel):
    """Immutable snapshot identifier with integrity validation.
    
    This model represents a deterministic snapshot ID computed as a
    SHA-256 hash of snapshot contents. The ID is validated to ensure
    it matches the expected SHA-256 hex format (64 hexadecimal characters).
    
    Attributes:
        id: SHA-256 hash string (64 hex characters)
    """
    
    model_config = {"frozen": True}
    
    id: str
    
    @field_validator('id')
    @classmethod
    def validate_sha256_hex(cls, v: str) -> str:
        """Validate that the ID matches SHA-256 hex pattern.
        
        Args:
            v: The ID string to validate
            
        Returns:
            The validated ID string
            
        Raises:
            ValueError: If the ID does not match SHA-256 hex pattern
        """
        sha256_pattern = re.compile(r'^[a-f0-9]{64}$', re.IGNORECASE)
        if not sha256_pattern.match(v):
            raise ValueError(
                f"SnapshotID must be a 64-character hexadecimal string (SHA-256), "
                f"got: {v[:20]}... (length: {len(v)})"
            )
        return v.lower()  # Normalize to lowercase for consistency


class SemanticGraph(BaseModel):
    """Immutable semantic graph container.
    
    This model represents the complete semantic graph constructed from
    metadata sources. It is a placeholder that will be expanded as the
    Safety Kernel implementation progresses.
    
    The raw_data field is excluded from serialization but holds the
    internal graph state for now.
    
    Attributes:
        raw_data: Internal dictionary holding graph state (excluded from serialization)
    """
    
    model_config = {"frozen": True}
    
    raw_data: dict = Field(default_factory=dict, exclude=True, alias="_raw_data")
    
    def __init__(self, **data):
        # Handle both _raw_data and raw_data for backward compatibility
        if "_raw_data" in data and "raw_data" not in data:
            data["raw_data"] = data.pop("_raw_data")
        super().__init__(**data)
    
    @property
    def _raw_data(self):
        """Backward compatibility property for _raw_data access."""
        return self.raw_data


class ProjectedGraph(BaseModel):
    """Immutable projected graph view for untrusted components.
    
    This model represents a filtered view of the semantic graph that has
    been processed by the Graph Projector to remove nodes/edges that the
    current user context is not permitted to access.
    
    The raw_data field is excluded from serialization but holds the
    filtered graph state.
    
    Attributes:
        raw_data: Internal dictionary holding filtered graph state (excluded from serialization)
    """
    
    model_config = {"frozen": True}
    
    raw_data: dict = Field(default_factory=dict, exclude=True)
    
    def __init__(self, **data):
        # Handle both _raw_data and raw_data for backward compatibility
        if "_raw_data" in data and "raw_data" not in data:
            data["raw_data"] = data.pop("_raw_data")
        super().__init__(**data)
    
    @property
    def _raw_data(self):
        """Backward compatibility property for _raw_data access."""
        return self.raw_data

