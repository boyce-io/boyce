"""Snapshot Store - Content-Addressable Storage for SemanticSnapshot.

This module provides content-addressable storage (CAS) for SemanticSnapshot objects,
keyed by their deterministic SHA-256 hash (snapshot_id).
"""

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

from datashark.core.types import SemanticSnapshot
from datashark.core.config import SNAPSHOT_DIR
from datashark_mcp.kernel.exceptions import SnapshotIntegrityError, SnapshotNotFoundError

logger = logging.getLogger(__name__)


class SnapshotStore:
    """Content-addressable storage for SemanticSnapshot objects.
    
    Stores snapshots as JSON files keyed by their SHA-256 hash (snapshot_id).
    Uses atomic writes to ensure consistency.
    """
    
    def __init__(self, snapshot_dir: Optional[Path] = None):
        """Initialize snapshot store.
        
        Args:
            snapshot_dir: Optional custom snapshot directory. Defaults to SNAPSHOT_DIR from config.
        """
        self.snapshot_dir = Path(snapshot_dir) if snapshot_dir else SNAPSHOT_DIR
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_snapshot_path(self, snapshot_id: str) -> Path:
        """Get filesystem path for a snapshot_id.
        
        Args:
            snapshot_id: SHA-256 hash string (64 hex chars)
            
        Returns:
            Path to snapshot JSON file
        """
        # Store as <snapshot_dir>/<snapshot_id>.json
        # Simple flat structure (no subdirectories for now)
        return self.snapshot_dir / f"{snapshot_id}.json"
    
    def _validate_no_secrets(self, snapshot: SemanticSnapshot) -> None:
        """Validate that snapshot.metadata does not contain obvious secret keys.
        
        Raises:
            SnapshotIntegrityError: If secret-like keys are detected
        """
        if not snapshot.metadata:
            return
        
        # Check for secret-like keys (case-insensitive)
        secret_key_patterns = [
            r"password",
            r"secret",
            r"token",
            r"apikey",
            r"api_key",
            r"authorization",
            r"auth",
            r"credential",
            r"private.*key",
        ]
        
        metadata_str = json.dumps(snapshot.metadata, sort_keys=True).lower()
        
        for pattern in secret_key_patterns:
            if re.search(pattern, metadata_str, re.IGNORECASE):
                raise SnapshotIntegrityError(
                    f"Snapshot metadata contains potential secret key matching pattern '{pattern}'. "
                    f"Secrets must be redacted before snapshot creation."
                )
    
    def _canonical_serialize(self, snapshot: SemanticSnapshot, exclude_snapshot_id: bool = True) -> bytes:
        """Serialize snapshot to canonical JSON bytes for hashing.
        
        Args:
            snapshot: SemanticSnapshot to serialize
            exclude_snapshot_id: If True, exclude snapshot_id from hash computation (default: True)
            
        Returns:
            Canonical JSON bytes (deterministic, sorted keys, compact format)
        """
        # Use model_dump to get dict representation
        snapshot_dict = snapshot.model_dump(mode='json')
        
        # Exclude snapshot_id from hash computation (it's derived from the hash)
        if exclude_snapshot_id and 'snapshot_id' in snapshot_dict:
            snapshot_dict = {k: v for k, v in snapshot_dict.items() if k != 'snapshot_id'}
        
        # Serialize with deterministic options
        snapshot_json = json.dumps(
            snapshot_dict,
            sort_keys=True,
            ensure_ascii=False,
            separators=(',', ':')  # Compact format (no extra whitespace)
        )
        
        return snapshot_json.encode('utf-8')
    
    def _compute_snapshot_id(self, snapshot: SemanticSnapshot) -> str:
        """Compute snapshot_id from canonical serialization.
        
        Args:
            snapshot: SemanticSnapshot to hash
            
        Returns:
            SHA-256 hash string (64 hex chars)
        """
        canonical_bytes = self._canonical_serialize(snapshot)
        hash_hex = hashlib.sha256(canonical_bytes).hexdigest()
        return hash_hex
    
    def save(self, snapshot: SemanticSnapshot) -> str:
        """Save snapshot to CAS and return snapshot_id.
        
        This method:
        1. Validates no secrets in metadata
        2. Computes snapshot_id from canonical serialization
        3. Writes snapshot to filesystem atomically
        4. Returns snapshot_id
        
        Args:
            snapshot: SemanticSnapshot to save (snapshot_id may be set or empty)
            
        Returns:
            snapshot_id (SHA-256 hash string)
            
        Raises:
            SnapshotIntegrityError: If secrets detected or save fails
        """
        # Step 1: Validate no secrets
        self._validate_no_secrets(snapshot)
        
        # Step 2: Compute snapshot_id from canonical serialization
        # This ensures snapshot_id matches the persisted bytes
        computed_id = self._compute_snapshot_id(snapshot)
        
        # Step 3: Update snapshot.snapshot_id if not set or mismatched
        # Note: Since SemanticSnapshot is frozen, we need to create new instance
        if snapshot.snapshot_id != computed_id:
            # Reconstruct snapshot with correct snapshot_id
            snapshot_dict = snapshot.model_dump()
            snapshot_dict['snapshot_id'] = computed_id
            snapshot = SemanticSnapshot(**snapshot_dict)
        
        # Step 4: Get target path
        snapshot_path = self._get_snapshot_path(computed_id)
        
        # Step 5: Atomic write (temp file + rename)
        import time
        tmp_suffix = f".{int(time.time() * 1000)}.tmp"
        tmp_path = snapshot_path.with_suffix(snapshot_path.suffix + tmp_suffix)
        
        try:
            # Serialize snapshot to JSON
            snapshot_dict = snapshot.model_dump(mode='json')
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(snapshot_dict, f, ensure_ascii=False, indent=2, sort_keys=True)
            
            # Atomic rename
            os.replace(tmp_path, snapshot_path)
            logger.debug(f"Saved snapshot {computed_id[:16]}... to {snapshot_path}")
            
        except Exception as e:
            # Clean up temp file on error
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
            raise SnapshotIntegrityError(
                f"Failed to save snapshot: {str(e)}"
            ) from e
        
        return computed_id
    
    def load(self, snapshot_id: str) -> SemanticSnapshot:
        """Load snapshot from CAS by hash.
        
        Args:
            snapshot_id: SHA-256 hash string (64 hex chars)
            
        Returns:
            SemanticSnapshot object
            
        Raises:
            SnapshotNotFoundError: If snapshot doesn't exist
            SnapshotIntegrityError: If loaded data doesn't match hash or deserialization fails
        """
        snapshot_path = self._get_snapshot_path(snapshot_id)
        
        if not snapshot_path.exists():
            raise SnapshotNotFoundError(
                f"Snapshot {snapshot_id[:16]}... not found at {snapshot_path}"
            )
        
        try:
            # Load JSON from file
            with open(snapshot_path, 'r', encoding='utf-8') as f:
                snapshot_dict = json.load(f)
            
            # Deserialize to SemanticSnapshot
            snapshot = SemanticSnapshot(**snapshot_dict)
            
            # Validate hash matches
            if snapshot.snapshot_id != snapshot_id:
                raise SnapshotIntegrityError(
                    f"Snapshot hash mismatch: expected {snapshot_id}, got {snapshot.snapshot_id}"
                )
            
            # Verify canonical serialization matches (defensive check)
            computed_id = self._compute_snapshot_id(snapshot)
            if computed_id != snapshot_id:
                raise SnapshotIntegrityError(
                    f"Snapshot canonical hash mismatch: file hash {snapshot_id}, computed {computed_id}"
                )
            
            logger.debug(f"Loaded snapshot {snapshot_id[:16]}... from {snapshot_path}")
            return snapshot
            
        except json.JSONDecodeError as e:
            raise SnapshotIntegrityError(
                f"Failed to parse snapshot JSON: {str(e)}"
            ) from e
        except Exception as e:
            if isinstance(e, (SnapshotNotFoundError, SnapshotIntegrityError)):
                raise
            raise SnapshotIntegrityError(
                f"Failed to load snapshot: {str(e)}"
            ) from e
    
    def exists(self, snapshot_id: str) -> bool:
        """Check if snapshot exists in CAS.
        
        Args:
            snapshot_id: SHA-256 hash string
            
        Returns:
            True if snapshot exists, False otherwise
        """
        snapshot_path = self._get_snapshot_path(snapshot_id)
        return snapshot_path.exists()
