"""
Model Storage

Lightweight on-disk model storage for DSL templates and join heuristics.
Uses JSON for deterministic, hash-tracked versioning.
"""

from __future__ import annotations

import json
import hashlib
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ModelStorage:
    """Manages on-disk model storage with versioning."""
    
    def __init__(self, instance_path: Path):
        """
        Initialize model storage.
        
        Args:
            instance_path: Path to instance directory
        """
        self.instance_path = instance_path
        self.models_dir = instance_path / "models"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initialized ModelStorage for instance: {instance_path}")
    
    def load_model(self, model_name: str) -> Optional[Dict[str, Any]]:
        """
        Load a model from disk.
        
        Args:
            model_name: Name of model (e.g., "dsl_templates", "join_heuristics")
            
        Returns:
            Model data or None if not found
        """
        model_path = self.models_dir / f"{model_name}.json"
        
        if not model_path.exists():
            return None
        
        try:
            with open(model_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load model {model_name}: {e}")
            return None
    
    def save_model(self, model_name: str, model_data: Dict[str, Any], seed: Optional[int] = None) -> str:
        """
        Save a model to disk with versioning.
        
        Args:
            model_name: Name of model
            model_data: Model data to save
            seed: Optional random seed for deterministic generation
            
        Returns:
            Model hash (version identifier)
        """
        from datashark_mcp.context.determinism import normalize_timestamp
        
        # Normalize timestamp for deterministic hashing
        # Use model content as key for normalization
        model_content = json.dumps(model_data, sort_keys=True)
        normalized_ts = normalize_timestamp(datetime.utcnow().isoformat() + "Z", content=model_content)
        
        # Add metadata
        model_with_meta = {
            "model_name": model_name,
            "version": model_data.get("version", "1.0.0"),
            "updated_at": normalized_ts,  # Normalized for determinism
            "seed": seed,
            "data": model_data
        }
        
        # Compute hash (exclude updated_at for hash computation to ensure determinism)
        # Use only model data and seed for hash
        hash_data = {
            "model_name": model_name,
            "version": model_data.get("version", "1.0.0"),
            "seed": seed,
            "data": model_data
        }
        model_str = json.dumps(hash_data, sort_keys=True)
        model_hash = hashlib.sha256(model_str.encode()).hexdigest()[:16]
        
        # Save model
        model_path = self.models_dir / f"{model_name}.json"
        
        with open(model_path, "w", encoding="utf-8") as f:
            json.dump(model_with_meta, f, indent=2)
        
        # Save version history
        history_path = self.models_dir / f"{model_name}_history.jsonl"
        with open(history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "timestamp": model_with_meta["updated_at"],
                "hash": model_hash,
                "version": model_with_meta["version"]
            }) + "\n")
        
        logger.info(f"Saved model {model_name} with hash {model_hash}")
        return model_hash
    
    def get_model_hash(self, model_name: str) -> Optional[str]:
        """Get current model hash."""
        model = self.load_model(model_name)
        if model:
            model_str = json.dumps(model, sort_keys=True)
            return hashlib.sha256(model_str.encode()).hexdigest()[:16]
        return None

