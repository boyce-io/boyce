"""
Instance Registry

Global registry for tracking all DataShark instances.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class InstanceRegistry:
    """Manages global instance registry."""
    
    def __init__(self, registry_path: Optional[Path] = None):
        """
        Initialize registry.
        
        Args:
            registry_path: Path to registry file (default: ~/.datashark/instances.json)
        """
        if registry_path is None:
            home = Path.home()
            datashark_dir = home / ".datashark"
            datashark_dir.mkdir(parents=True, exist_ok=True)
            registry_path = datashark_dir / "instances.json"
        
        self.registry_path = registry_path
        self._registry: Dict[str, Any] = {}
        self._load()
    
    def _load(self) -> None:
        """Load registry from file."""
        if self.registry_path.exists():
            try:
                with open(self.registry_path, 'r', encoding='utf-8') as f:
                    self._registry = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load registry: {e}")
                self._registry = {"active": None, "instances": {}}
        else:
            self._registry = {"active": None, "instances": {}}
    
    def _save(self) -> None:
        """Save registry to file."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.registry_path, 'w', encoding='utf-8') as f:
            json.dump(self._registry, f, indent=2, ensure_ascii=False)
    
    def load_registry(self) -> Dict[str, Any]:
        """Get full registry data."""
        self._load()
        return self._registry.copy()
    
    def save_registry(self, registry: Dict[str, Any]) -> None:
        """Save full registry (use with caution)."""
        self._registry = registry
        self._save()
    
    def add_instance(self, name: str, path: Path, version: str = "0.2.0") -> None:
        """
        Add instance to registry.
        
        Args:
            name: Instance name
            path: Instance directory path
            version: Framework version
        """
        if "instances" not in self._registry:
            self._registry["instances"] = {}
        
        self._registry["instances"][name] = {
            "path": str(path),
            "version": version,
            "created": datetime.utcnow().isoformat() + "Z"
        }
        self._save()
        logger.info(f"Added instance '{name}' to registry")
    
    def remove_instance(self, name: str) -> None:
        """
        Remove instance from registry.
        
        Args:
            name: Instance name
        """
        if "instances" in self._registry and name in self._registry["instances"]:
            del self._registry["instances"][name]
            
            # If it was active, clear active
            if self._registry.get("active") == name:
                self._registry["active"] = None
            
            self._save()
            logger.info(f"Removed instance '{name}' from registry")
        else:
            logger.warning(f"Instance '{name}' not found in registry")
    
    def set_active_instance(self, name: str) -> None:
        """
        Set active instance.
        
        Args:
            name: Instance name
        """
        if "instances" not in self._registry or name not in self._registry["instances"]:
            raise ValueError(f"Instance '{name}' not found in registry")
        
        self._registry["active"] = name
        self._save()
        logger.info(f"Set active instance to '{name}'")
    
    def get_active_instance(self) -> Optional[Dict[str, Any]]:
        """
        Get active instance info.
        
        Returns:
            Instance dict or None if no active instance
        """
        active_name = self._registry.get("active")
        if active_name and "instances" in self._registry:
            return self._registry["instances"].get(active_name)
        return None
    
    def list_instances(self) -> Dict[str, Dict[str, Any]]:
        """
        List all instances.
        
        Returns:
            Dict of instance name -> instance info
        """
        return self._registry.get("instances", {}).copy()
    
    def get_instance(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get instance info by name.
        
        Args:
            name: Instance name
        
        Returns:
            Instance dict or None
        """
        return self._registry.get("instances", {}).get(name)

