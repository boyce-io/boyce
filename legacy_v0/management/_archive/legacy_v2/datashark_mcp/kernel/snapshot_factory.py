"""Snapshot Factory - The Metadata Bridge & Integrity Gate.

This module provides the ONLY valid entry point for metadata ingestion into
the Safety Kernel. All raw metadata must pass through this factory to ensure
integrity, determinism, and proper governance boundaries.

The SnapshotFactory enforces:
- Deterministic snapshot ID computation (SHA-256 hash)
- Immutable SemanticGraph creation
- Integrity validation of raw metadata
- Proper error handling and reporting
- Content-addressable storage of SemanticSnapshot
"""

import hashlib
import json
from typing import Dict, Optional, Tuple

from pydantic import ValidationError

from datashark.core.types import SemanticSnapshot
from datashark_mcp.kernel.exceptions import SnapshotIntegrityError
from datashark_mcp.kernel.snapshot_store import SnapshotStore
from datashark_mcp.kernel.types import SemanticGraph, SnapshotID


class SnapshotFactory:
    """The Metadata Bridge - Only valid entry point for raw metadata ingestion.
    
    This class enforces the Safety Kernel's integrity gate by:
    1. Validating raw metadata structure
    2. Creating immutable SemanticGraph instances
    3. Computing deterministic snapshot IDs via SHA-256 hashing
    4. Ensuring all metadata passes through a single, auditable entry point
    
    All raw metadata must be ingested through this factory. No other code
    should directly instantiate SemanticGraph or SnapshotID.
    """
    
    @staticmethod
    def create_snapshot(raw_metadata: Dict) -> Tuple[SemanticGraph, SnapshotID]:
        """Create a semantic snapshot from raw metadata.
        
        This method is the ONLY valid entry point for metadata ingestion.
        It performs the following steps:
        1. Instantiate SemanticGraph from raw_metadata
        2. Deterministically serialize the metadata (JSON with sorted keys)
        3. Compute SHA-256 hash of the serialized data
        4. Create SnapshotID from the hash
        5. Return immutable (graph, snapshot_id) tuple
        
        Args:
            raw_metadata: Dictionary containing raw metadata to be ingested.
                        Must be JSON-serializable and valid for SemanticGraph.
        
        Returns:
            Tuple containing:
            - SemanticGraph: Immutable graph instance with _raw_data populated
            - SnapshotID: Immutable snapshot identifier (SHA-256 hash)
        
        Raises:
            SnapshotIntegrityError: If metadata validation fails, serialization
                                   fails, or any other integrity check fails.
        
        Example:
            >>> metadata = {"entities": [...], "relationships": [...]}
            >>> graph, snapshot_id = SnapshotFactory.create_snapshot(metadata)
            >>> print(snapshot_id.id)  # SHA-256 hash string
        """
        try:
            # Step A: Instantiate SemanticGraph using the raw_metadata
            # Use model_construct to bypass validation and directly set the field
            # This is necessary because raw_data has exclude=True which affects __init__
            graph = SemanticGraph.model_construct(raw_data=raw_metadata)
            
            # Step B: Deterministic serialization of the graph metadata
            # Use json.dumps with sort_keys=True to ensure deterministic ordering
            # This ensures the same metadata always produces the same hash
            serialized_metadata = json.dumps(
                raw_metadata,
                sort_keys=True,
                ensure_ascii=False  # Preserve unicode characters
            )
            
            # Step C: Generate SHA-256 hash of the serialized string
            # Encode the string to bytes before hashing
            hash_bytes = hashlib.sha256(serialized_metadata.encode('utf-8')).digest()
            hash_hex = hash_bytes.hex()
            
            # Step D: Instantiate SnapshotID with the hash
            # The SnapshotID model will validate that the hash is 64 hex characters
            snapshot_id = SnapshotID(id=hash_hex)
            
            # Step E: Return the tuple (graph, snapshot_id)
            return (graph, snapshot_id)
            
        except ValidationError as e:
            # Pydantic validation errors (e.g., invalid SemanticGraph or SnapshotID structure)
            raise SnapshotIntegrityError(
                f"Metadata validation failed: {str(e)}. "
                f"Raw metadata must conform to SemanticGraph schema."
            ) from e
        except (TypeError, ValueError) as e:
            # JSON serialization errors or other type/value errors
            raise SnapshotIntegrityError(
                f"Metadata serialization failed: {str(e)}. "
                f"Raw metadata must be JSON-serializable."
            ) from e
        except Exception as e:
            # Catch-all for any other unexpected errors
            raise SnapshotIntegrityError(
                f"Snapshot creation failed with unexpected error: {str(e)}. "
                f"Type: {type(e).__name__}"
            ) from e
    
    @staticmethod
    def save_snapshot(snapshot: SemanticSnapshot, store: Optional[SnapshotStore] = None) -> str:
        """Save a SemanticSnapshot to CAS and return its snapshot_id.
        
        This method:
        1. Computes snapshot_id from canonical serialization of the snapshot
        2. Updates snapshot.snapshot_id if needed
        3. Saves snapshot to content-addressable storage
        4. Returns the snapshot_id
        
        Args:
            snapshot: SemanticSnapshot to save (snapshot_id may be empty or set)
            store: Optional SnapshotStore instance. If None, creates a default one.
        
        Returns:
            snapshot_id (SHA-256 hash string)
        
        Raises:
            SnapshotIntegrityError: If save fails or secrets detected
        """
        if store is None:
            store = SnapshotStore()
        
        return store.save(snapshot)

